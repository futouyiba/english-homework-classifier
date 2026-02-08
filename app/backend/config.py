from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
VAULT_ROOT: Final[Path] = PROJECT_ROOT / "HomeworkVault"
INBOX_DIR: Final[Path] = VAULT_ROOT / "Inbox"
LIBRARY_DIR: Final[Path] = VAULT_ROOT / "Library"
LIBRARY_VOCAB_DIR: Final[Path] = LIBRARY_DIR / "Vocab"
LIBRARY_SENTENCE_DIR: Final[Path] = LIBRARY_DIR / "Sentences"
LIBRARY_FASTSTORY_DIR: Final[Path] = LIBRARY_DIR / "FastStory"
DAILY_DIR: Final[Path] = VAULT_ROOT / "Daily"
CONFIG_DIR: Final[Path] = VAULT_ROOT / "Config"
REPORTS_DIR: Final[Path] = VAULT_ROOT / "Reports"
MAPPINGS_PATH: Final[Path] = CONFIG_DIR / "mappings.json"
TEACHER_CMD_PATH: Final[Path] = CONFIG_DIR / "teacher_cmd.txt"
INBOX_ITEMS_PATH: Final[Path] = REPORTS_DIR / "inbox_items.json"

AUDIO_EXTENSIONS: Final[set[str]] = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg"}


@dataclass(frozen=True)
class RuntimeSettings:
    asr_engine: str
    asr_process_scope: str
    asr_tag_window_sec: int
    whisper_model: str
    whisper_language: str
    openai_model: str
    openai_api_key: str | None
    openai_base_url: str | None


def load_runtime_settings() -> RuntimeSettings:
    asr_engine = os.getenv("ASR_ENGINE", "whisper_local").strip().lower()
    if asr_engine not in {"whisper_local", "openai_api", "stub"}:
        asr_engine = "whisper_local"

    asr_process_scope = os.getenv("ASR_PROCESS_SCOPE", "hybrid").strip().lower()
    if asr_process_scope not in {"head", "full", "hybrid"}:
        asr_process_scope = "hybrid"

    raw_window = os.getenv("ASR_TAG_WINDOW_SEC", "20").strip()
    try:
        asr_tag_window_sec = max(1, int(raw_window))
    except ValueError:
        asr_tag_window_sec = 20

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
    openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None

    return RuntimeSettings(
        asr_engine=asr_engine,
        asr_process_scope=asr_process_scope,
        asr_tag_window_sec=asr_tag_window_sec,
        whisper_model=os.getenv("WHISPER_MODEL", "small").strip(),
        whisper_language=os.getenv("WHISPER_LANGUAGE", "zh").strip(),
        openai_model=os.getenv("OPENAI_ASR_MODEL", "whisper-1").strip(),
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
    )


def _default_items(max_index: int, zh_prefix: str, en_prefix: str) -> dict[str, dict[str, object]]:
    items: dict[str, dict[str, object]] = {}
    for idx in range(1, max_index + 1):
        title_zh = f"{zh_prefix}{idx:02d}"
        title_en = f"{en_prefix}{idx:02d}"
        items[str(idx)] = {
            "title_zh": title_zh,
            "title_en": title_en,
            "synonyms": [
                title_zh,
                title_en,
                f"第{idx}类",
                f"{idx}类",
            ],
        }
    return items


def build_default_mappings() -> dict[str, object]:
    mappings = {
        "VOCAB": {
            "max_index": 17,
            "items": _default_items(17, "词汇", "Vocab"),
        },
        "SENTENCE": {
            "max_index": 15,
            "items": _default_items(15, "句子", "Sentence"),
        },
        "FASTSTORY": {
            "max_index": 6,
            "items": _default_items(6, "快嘴", "FastStory"),
        },
        "GLOBAL_SYNONYMS": {
            "VOCAB": ["词汇", "单词", "词组", "vocab"],
            "SENTENCE": ["句子", "句型", "sentence"],
            "FASTSTORY": ["快嘴", "阅读", "小短文", "story"],
        },
    }

    # Seed examples from the requirement document.
    mappings["VOCAB"]["items"]["7"] = {  # type: ignore[index]
        "title_zh": "颜色",
        "title_en": "Color",
        "synonyms": ["颜色", "color", "第七类", "7类", "七类"],
    }
    mappings["SENTENCE"]["items"]["5"] = {  # type: ignore[index]
        "title_zh": "数量相关",
        "title_en": "Quantity",
        "synonyms": ["数量", "数量相关", "第5类", "五类", "句子五"],
    }
    mappings["FASTSTORY"]["items"]["3"] = {  # type: ignore[index]
        "title_zh": "A super player",
        "title_en": "A super player",
        "synonyms": ["第三篇", "第3篇", "3篇", "A super player", "super player"],
    }

    return mappings


def ensure_bootstrap() -> None:
    for path in (
        INBOX_DIR,
        LIBRARY_VOCAB_DIR,
        LIBRARY_SENTENCE_DIR,
        LIBRARY_FASTSTORY_DIR,
        DAILY_DIR,
        CONFIG_DIR,
        REPORTS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)

    if not MAPPINGS_PATH.exists():
        MAPPINGS_PATH.write_text(
            json.dumps(build_default_mappings(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if not TEACHER_CMD_PATH.exists():
        TEACHER_CMD_PATH.write_text("", encoding="utf-8")

    if not INBOX_ITEMS_PATH.exists():
        INBOX_ITEMS_PATH.write_text("[]", encoding="utf-8")
