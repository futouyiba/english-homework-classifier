from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import (
    AUDIO_EXTENSIONS,
    DAILY_DIR,
    INBOX_DIR,
    INBOX_ITEMS_PATH,
    LIBRARY_FASTSTORY_DIR,
    LIBRARY_SENTENCE_DIR,
    LIBRARY_VOCAB_DIR,
    MAPPINGS_PATH,
    PROJECT_ROOT,
    TEACHER_CMD_PATH,
    ensure_bootstrap,
    load_runtime_settings,
)
from .asr import transcribe_for_scope

TYPE_TO_LIBRARY = {
    "VOCAB": LIBRARY_VOCAB_DIR,
    "SENTENCE": LIBRARY_SENTENCE_DIR,
    "FASTSTORY": LIBRARY_FASTSTORY_DIR,
}
TYPE_TO_CODE = {"VOCAB": "C", "SENTENCE": "S", "FASTSTORY": "P"}
TYPE_TO_CN = {"VOCAB": "词汇", "SENTENCE": "句子", "FASTSTORY": "快嘴"}
logger = logging.getLogger(__name__)

CN_NUM_MAP = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


@dataclass
class TagResult:
    type: str
    index: int
    title_zh: str
    title_en: str
    confidence: float
    signals: dict[str, Any]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _to_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def load_mappings() -> dict[str, Any]:
    ensure_bootstrap()
    return json.loads(MAPPINGS_PATH.read_text(encoding="utf-8"))


def save_mappings(payload: dict[str, Any]) -> None:
    MAPPINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_items() -> list[dict[str, Any]]:
    ensure_bootstrap()
    raw = INBOX_ITEMS_PATH.read_text(encoding="utf-8")
    return json.loads(raw) if raw.strip() else []


def _save_items(items: list[dict[str, Any]]) -> None:
    INBOX_ITEMS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_type(raw_type: str) -> str:
    value = raw_type.upper()
    if value not in TYPE_TO_LIBRARY:
        raise ValueError(f"Unsupported type: {raw_type}")
    return value


def _cn_num_to_int(text: str) -> int | None:
    token = text.strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)

    if token == "十":
        return 10
    if "十" in token:
        parts = token.split("十")
        left = CN_NUM_MAP.get(parts[0], 1) if parts[0] else 1
        right = CN_NUM_MAP.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return left * 10 + right

    total = 0
    for ch in token:
        if ch not in CN_NUM_MAP:
            return None
        total = total * 10 + CN_NUM_MAP[ch]
    return total


def _is_valid_index(item_type: str, index: int, mappings: dict[str, Any]) -> bool:
    max_index = int(mappings[item_type]["max_index"])
    return 1 <= index <= max_index


def _resolve_item(item_type: str, index: int, mappings: dict[str, Any]) -> dict[str, Any]:
    return mappings[item_type]["items"].get(str(index), {})


def _library_item_dir(item_type: str, index: int, title_zh: str, title_en: str) -> Path:
    base = TYPE_TO_LIBRARY[item_type]
    code = TYPE_TO_CODE[item_type]
    prefix = f"{code}{index:02d}_"

    existing = sorted(base.glob(f"{prefix}*"))
    if existing:
        return existing[0]

    if item_type == "FASTSTORY":
        raw = title_en or title_zh or f"story_{index:02d}"
        safe = re.sub(r"\s+", "_", raw.strip())
        safe = re.sub(r"[\\\\/:*?\"<>|]", "_", safe)
        folder = base / f"{prefix}{safe}"
    else:
        folder = base / f"{prefix}{title_zh}({title_en})"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _archive_audio(src_path: Path, tag: TagResult, mappings: dict[str, Any], remove_source: bool) -> str:
    target_dir = _library_item_dir(tag.type, tag.index, tag.title_zh, tag.title_en)
    ext = src_path.suffix.lower() or ".m4a"
    target = target_dir / f"take_{_now_stamp()}{ext}"
    shutil.copy2(src_path, target)

    if remove_source and src_path.exists() and src_path.parent.resolve() == INBOX_DIR.resolve():
        src_path.unlink()

    return _to_relative(target)


def _type_keywords(mappings: dict[str, Any]) -> dict[str, list[str]]:
    global_syn = mappings.get("GLOBAL_SYNONYMS", {})
    return {
        "VOCAB": [k.lower() for k in global_syn.get("VOCAB", [])] + ["vocab"],
        "SENTENCE": [k.lower() for k in global_syn.get("SENTENCE", [])] + ["sentence"],
        "FASTSTORY": [k.lower() for k in global_syn.get("FASTSTORY", [])] + ["faststory", "story"],
    }


def _infer_tag_from_text(text: str, mappings: dict[str, Any]) -> TagResult:
    s = text.strip()
    lower = s.lower()
    signals: dict[str, Any] = {"hit_keywords": [], "raw_number_forms": [], "raw_title_forms": []}

    code_match = re.search(
        r"(?:^|[^A-Za-z0-9])([CSP])\s*0?(\d{1,2})(?=$|[^A-Za-z0-9])",
        s,
        flags=re.IGNORECASE,
    )
    if code_match:
        code, num_raw = code_match.group(1).upper(), code_match.group(2)
        item_type = {"C": "VOCAB", "S": "SENTENCE", "P": "FASTSTORY"}[code]
        index = int(num_raw)
        if _is_valid_index(item_type, index, mappings):
            item = _resolve_item(item_type, index, mappings)
            return TagResult(
                type=item_type,
                index=index,
                title_zh=item.get("title_zh", ""),
                title_en=item.get("title_en", ""),
                confidence=0.95,
                signals=signals,
            )

    detected_type: str | None = None
    for item_type, kws in _type_keywords(mappings).items():
        for kw in kws:
            if kw and kw in lower:
                signals["hit_keywords"].append(kw)
                detected_type = item_type
                break
        if detected_type:
            break

    title_hit: tuple[str, int, dict[str, Any], str] | None = None
    for item_type in ("VOCAB", "SENTENCE", "FASTSTORY"):
        for idx_str, item in mappings[item_type]["items"].items():
            for syn in item.get("synonyms", []):
                syn_text = str(syn).strip()
                if not syn_text or syn_text.isdigit():
                    continue
                if syn_text.lower() in lower:
                    signals["raw_title_forms"].append(syn_text)
                    title_hit = (item_type, int(idx_str), item, syn)
                    break
            if title_hit:
                break
        if title_hit:
            break

    num_match = re.search(r"(?:第)?([一二三四五六七八九十两0-9]{1,3})(?:类|篇)?", s)
    index: int | None = None
    if num_match:
        raw_num = num_match.group(1)
        signals["raw_number_forms"].append(raw_num)
        index = _cn_num_to_int(raw_num)

    if title_hit and (detected_type is None or detected_type == title_hit[0]):
        item_type, hit_index, item, _ = title_hit
        confidence = 0.8 if detected_type else 0.75
        return TagResult(
            type=item_type,
            index=hit_index,
            title_zh=item.get("title_zh", ""),
            title_en=item.get("title_en", ""),
            confidence=confidence,
            signals=signals,
        )

    if detected_type and index and _is_valid_index(detected_type, index, mappings):
        item = _resolve_item(detected_type, index, mappings)
        return TagResult(
            type=detected_type,
            index=index,
            title_zh=item.get("title_zh", ""),
            title_en=item.get("title_en", ""),
            confidence=0.85,
            signals=signals,
        )

    fallback_type = detected_type or "VOCAB"
    fallback_index = index if index and _is_valid_index(fallback_type, index, mappings) else 1
    fallback_item = _resolve_item(fallback_type, fallback_index, mappings)
    return TagResult(
        type=fallback_type,
        index=fallback_index,
        title_zh=fallback_item.get("title_zh", ""),
        title_en=fallback_item.get("title_en", ""),
        confidence=0.3 if detected_type else 0.2,
        signals=signals,
    )


def process_audio_file(path_value: str) -> dict[str, Any]:
    ensure_bootstrap()
    mappings = load_mappings()
    runtime = load_runtime_settings()

    src = Path(path_value)
    if not src.is_absolute():
        src = (PROJECT_ROOT / path_value).resolve()

    if not src.exists():
        raise FileNotFoundError(str(src))

    asr_result, head_text, asr_debug = transcribe_for_scope(
        src,
        runtime,
        scope=runtime.asr_process_scope,
    )
    tag_source_text = head_text or asr_result.text or src.stem
    tag = _infer_tag_from_text(tag_source_text, mappings)
    needs_review = tag.confidence < 0.75
    library_path = ""
    if not needs_review:
        library_path = _archive_audio(src, tag, mappings, remove_source=True)
    logger.info(
        "Processed audio: src=%s engine=%s scope=%s confidence=%.2f type=%s index=%s needs_review=%s",
        src,
        asr_result.engine,
        asr_debug.get("scope"),
        tag.confidence,
        tag.type,
        tag.index,
        needs_review,
    )

    record = {
        "id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "src_path": _to_relative(src),
        "duration_sec": asr_result.duration_sec,
        "asr": {
            "engine": asr_result.engine,
            "text": asr_result.text,
            "lang": asr_result.lang,
            "segments": asr_result.segments,
            "tag_window_text": head_text,
            "scope": asr_debug.get("scope"),
            "debug": asr_debug,
        },
        "tag": {
            "type": tag.type,
            "index": tag.index,
            "title_zh": tag.title_zh,
            "title_en": tag.title_en,
            "confidence": tag.confidence,
            "signals": tag.signals,
        },
        "library_path": library_path,
        "needs_review": needs_review,
    }

    items = _load_items()
    items.append(record)
    _save_items(items)
    return record


def preview_tag_for_text(text: str) -> dict[str, Any]:
    mappings = load_mappings()
    tag = _infer_tag_from_text(text, mappings)
    return {
        "type": tag.type,
        "index": tag.index,
        "title_zh": tag.title_zh,
        "title_en": tag.title_en,
        "confidence": tag.confidence,
        "signals": tag.signals,
    }


def list_recent_items(limit: int = 200) -> list[dict[str, Any]]:
    items = _load_items()
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items[:limit]


def scan_inbox() -> dict[str, int]:
    ensure_bootstrap()
    queued = 0
    processed = 0
    failed = 0
    for file in sorted(INBOX_DIR.iterdir()):
        if not file.is_file():
            continue
        if file.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        queued += 1
        try:
            process_audio_file(str(file))
            processed += 1
        except Exception:
            failed += 1
    return {"queued": queued, "processed": processed, "failed": failed}


def relabel_item(item_id: str, item_type: str, index: int, title_zh: str, title_en: str) -> dict[str, Any]:
    ensure_bootstrap()
    mappings = load_mappings()
    item_type = _normalize_type(item_type)
    if not _is_valid_index(item_type, index, mappings):
        raise ValueError(f"Invalid index {index} for type {item_type}")

    items = _load_items()
    target = next((x for x in items if x.get("id") == item_id), None)
    if not target:
        raise LookupError(f"Item not found: {item_id}")

    src = Path(target["src_path"])
    if not src.is_absolute():
        src = (PROJECT_ROOT / target["src_path"]).resolve()
    if not src.exists():
        raise FileNotFoundError(str(src))

    item_meta = _resolve_item(item_type, index, mappings)
    final_title_zh = title_zh or item_meta.get("title_zh", "")
    final_title_en = title_en or item_meta.get("title_en", "")

    tag = TagResult(
        type=item_type,
        index=index,
        title_zh=final_title_zh,
        title_en=final_title_en,
        confidence=1.0,
        signals={"manual_override": True},
    )
    library_path = _archive_audio(src, tag, mappings, remove_source=True)

    target["tag"] = {
        "type": item_type,
        "index": index,
        "title_zh": final_title_zh,
        "title_en": final_title_en,
        "confidence": 1.0,
        "signals": {"manual_override": True},
    }
    target["library_path"] = library_path
    target["needs_review"] = False
    target["updated_at"] = _now_iso()
    _save_items(items)
    return {"ok": True, "library_path": library_path}


def _find_library_dir_for_index(item_type: str, index: int, mappings: dict[str, Any]) -> Path | None:
    base = TYPE_TO_LIBRARY[item_type]
    code = TYPE_TO_CODE[item_type]
    matches = sorted(base.glob(f"{code}{index:02d}_*"))
    if matches:
        return matches[0]

    meta = _resolve_item(item_type, index, mappings)
    if not meta:
        return None
    candidate = _library_item_dir(item_type, index, meta.get("title_zh", ""), meta.get("title_en", ""))
    return candidate if candidate.exists() else None


def library_summary() -> list[dict[str, Any]]:
    mappings = load_mappings()
    rows: list[dict[str, Any]] = []
    for item_type in ("VOCAB", "SENTENCE", "FASTSTORY"):
        max_index = int(mappings[item_type]["max_index"])
        for idx in range(1, max_index + 1):
            meta = _resolve_item(item_type, idx, mappings)
            folder = _find_library_dir_for_index(item_type, idx, mappings)
            takes: list[Path] = []
            if folder and folder.exists():
                takes = sorted(folder.glob("take_*"), reverse=True)
            rows.append(
                {
                    "type": item_type,
                    "index": idx,
                    "title_zh": meta.get("title_zh", ""),
                    "title_en": meta.get("title_en", ""),
                    "take_count": len(takes),
                    "latest_time": takes[0].name if takes else "",
                }
            )
    return rows


def library_takes(item_type: str, index: int) -> dict[str, Any]:
    mappings = load_mappings()
    item_type = _normalize_type(item_type)
    if not _is_valid_index(item_type, index, mappings):
        raise ValueError(f"Invalid index {index} for type {item_type}")

    folder = _find_library_dir_for_index(item_type, index, mappings)
    takes: list[dict[str, str]] = []
    if folder and folder.exists():
        for file in sorted(folder.glob("take_*"), reverse=True):
            if file.is_file():
                takes.append({"name": file.name, "path": _to_relative(file)})
    return {"type": item_type, "index": index, "takes": takes}


def _extract_indices(text: str, pattern: str) -> set[int]:
    found: set[int] = set()
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        raw = match.group(1)
        value = _cn_num_to_int(raw)
        if value:
            found.add(value)
    return found


def parse_teacher_command(text: str) -> dict[str, Any]:
    mappings = load_mappings()
    normalized = re.sub(r"\s+", "", text)
    needs = {"SENTENCE": set(), "VOCAB": set(), "FASTSTORY": set()}

    needs["SENTENCE"] |= _extract_indices(normalized, r"(?:句子|句型)([一二三四五六七八九十两0-9]{1,3})")
    needs["VOCAB"] |= _extract_indices(normalized, r"(?:词汇|单词|词组)([一二三四五六七八九十两0-9]{1,3})")
    needs["FASTSTORY"] |= _extract_indices(normalized, r"(?:快嘴|阅读|短文)(?:第)?([一二三四五六七八九十两0-9]{1,3})(?:篇)?")

    # Chunk parsing improves robustness for phrases like "词汇七和11".
    sentence_keys = ("句子", "句型")
    vocab_keys = ("词汇", "单词", "词组")
    story_keys = ("快嘴", "阅读", "短文")
    for chunk in re.split(r"[，,。；;、\n]", normalized):
        if not chunk:
            continue
        target_type: str | None = None
        if any(k in chunk for k in sentence_keys):
            target_type = "SENTENCE"
        elif any(k in chunk for k in vocab_keys):
            target_type = "VOCAB"
        elif any(k in chunk for k in story_keys):
            target_type = "FASTSTORY"
        if not target_type:
            continue
        for raw in re.findall(r"(?:第)?([一二三四五六七八九十两0-9]{1,3})(?:类|篇)?", chunk):
            value = _cn_num_to_int(raw)
            if value:
                needs[target_type].add(value)

    needs["SENTENCE"] |= _extract_indices(normalized, r"(?:^|[^A-Za-z0-9])S0?([0-9]{1,2})(?=$|[^0-9])")
    needs["VOCAB"] |= _extract_indices(normalized, r"(?:^|[^A-Za-z0-9])C0?([0-9]{1,2})(?=$|[^0-9])")
    needs["FASTSTORY"] |= _extract_indices(normalized, r"(?:^|[^A-Za-z0-9])P0?([0-9]{1,2})(?=$|[^0-9])")
    for code_match in re.finditer(r"([CSP])0?([0-9]{1,2})", normalized, flags=re.IGNORECASE):
        code = code_match.group(1).upper()
        idx = int(code_match.group(2))
        if code == "C":
            needs["VOCAB"].add(idx)
        elif code == "S":
            needs["SENTENCE"].add(idx)
        else:
            needs["FASTSTORY"].add(idx)
    needs["FASTSTORY"] |= _extract_indices(normalized, r"第([一二三四五六七八九十两0-9]{1,3})篇")

    lower = normalized.lower()
    for item_type in ("VOCAB", "SENTENCE", "FASTSTORY"):
        for idx_str, meta in mappings[item_type]["items"].items():
            for syn in meta.get("synonyms", []):
                syn_text = str(syn).strip()
                if not syn_text or syn_text.isdigit():
                    continue
                if syn_text and syn_text.lower() in lower:
                    needs[item_type].add(int(idx_str))
                    break

    cleaned: dict[str, list[int]] = {}
    for item_type in ("SENTENCE", "VOCAB", "FASTSTORY"):
        max_index = int(mappings[item_type]["max_index"])
        values = sorted(x for x in needs[item_type] if 1 <= x <= max_index)
        cleaned[item_type] = values

    TEACHER_CMD_PATH.write_text(text, encoding="utf-8")
    return {"date": str(date.today()), "needs": cleaned}


def _format_code(item_type: str, index: int) -> str:
    return f"{TYPE_TO_CODE[item_type]}{index:02d}"


def build_daily_package(date_str: str, teacher_cmd: str, needs: dict[str, list[int]]) -> dict[str, Any]:
    mappings = load_mappings()
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    day_dir = DAILY_DIR / target_date.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    missing: list[dict[str, Any]] = []
    copied = 0
    report_lines = [
        f"日期：{target_date.strftime('%Y-%m-%d')}",
        f"老师指令：{teacher_cmd}",
        "",
        "需求清单：",
    ]

    for item_type in ("SENTENCE", "VOCAB", "FASTSTORY"):
        indexes = sorted(set(needs.get(item_type, [])))
        labels: list[str] = []
        for idx in indexes:
            if not _is_valid_index(item_type, idx, mappings):
                continue
            meta = _resolve_item(item_type, idx, mappings)
            labels.append(f"{_format_code(item_type, idx)} {meta.get('title_zh', '')}".strip())
        report_lines.append(f"- {TYPE_TO_CN[item_type]}：{'；'.join(labels) if labels else '无'}")

    report_lines.append("")
    report_lines.append("覆盖率：")

    for item_type in ("SENTENCE", "VOCAB", "FASTSTORY"):
        indexes = sorted(set(needs.get(item_type, [])))
        cn_dir = day_dir / TYPE_TO_CN[item_type]
        cn_dir.mkdir(parents=True, exist_ok=True)
        for idx in indexes:
            if not _is_valid_index(item_type, idx, mappings):
                continue
            meta = _resolve_item(item_type, idx, mappings)
            folder = _find_library_dir_for_index(item_type, idx, mappings)
            takes: list[Path] = []
            if folder and folder.exists():
                takes = sorted([p for p in folder.glob("take_*") if p.is_file()], reverse=True)

            selected = takes[:2]
            code = _format_code(item_type, idx)
            for i, src in enumerate(selected, start=1):
                ext = src.suffix.lower() or ".m4a"
                dst_name = f"{TYPE_TO_CN[item_type]}_{code}_{meta.get('title_zh', '')}_take{i}{ext}"
                dst_name = re.sub(r"[\\\\/:*?\"<>|]", "_", dst_name)
                shutil.copy2(src, cn_dir / dst_name)
                copied += 1

            if len(selected) < 2:
                missing_count = 2 - len(selected)
                missing.append({"type": item_type, "index": idx, "missing_count": missing_count})
                report_lines.append(
                    f"- {TYPE_TO_CN[item_type]} {code}：可用 {len(takes)} 条，仅打包 {len(selected)} 条 ⚠ 缺 {missing_count} 条"
                )
            else:
                report_lines.append(
                    f"- {TYPE_TO_CN[item_type]} {code}：可用 {len(takes)} 条，已打包 2 条 ✓"
                )

    report_path = day_dir / "_report.txt"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return {
        "daily_dir": _to_relative(day_dir),
        "copied": copied,
        "missing": missing,
        "report_path": _to_relative(report_path),
    }
