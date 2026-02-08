from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from pypdf import PdfReader


def u(s: str) -> str:
    return s.encode("ascii").decode("unicode_escape")


def extract_sources(src_dir: Path, converted_dir: Path) -> tuple[Path, Path]:
    converted_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(src_dir.glob("*.pdf"))
    docx_files = sorted(src_dir.glob("*.docx"))
    if not pdf_files or not docx_files:
        raise FileNotFoundError("originalText 目录缺少 pdf/docx 文件")

    pdf_path = pdf_files[0]
    pdf_reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for i, page in enumerate(pdf_reader.pages, start=1):
        pages.append(f"\n\n===== PAGE {i} =====\n{page.extract_text() or ''}")
    pdf_out = converted_dir / f"{pdf_path.stem}.txt"
    pdf_out.write_text("".join(pages), encoding="utf-8")

    docx_path = docx_files[0]
    doc = Document(str(docx_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    docx_out = converted_dir / f"{docx_path.stem}.txt"
    docx_out.write_text("\n".join(paragraphs), encoding="utf-8")

    return pdf_out, docx_out


def build_structured(converted_dir: Path, structured_dir: Path, config_mappings_path: Path) -> None:
    structured_dir.mkdir(parents=True, exist_ok=True)
    txt_files = list(converted_dir.glob("*.txt"))
    if len(txt_files) < 2:
        raise FileNotFoundError("converted 目录缺少提取后的 txt 文件")

    # Keep deterministic: longer text is PDF summary, shorter is DOCX stories.
    text_map = {p: p.read_text(encoding="utf-8") for p in txt_files}
    pdf_txt = max(txt_files, key=lambda p: len(text_map[p]))
    doc_txt = min(txt_files, key=lambda p: len(text_map[p]))
    doc_lines = [ln.strip() for ln in text_map[doc_txt].splitlines() if ln.strip()]

    vocab_titles = [
        u("\\u65f6\\u95f4"),
        u("\\u5730\\u70b9"),
        u("\\u52a8\\u7269"),
        u("\\u5929\\u6c14"),
        u("\\u6570\\u5b57"),
        u("\\u4ea4\\u901a\\u5de5\\u5177"),
        u("\\u989c\\u8272"),
        u("\\u4eba\\u7269"),
        u("\\u7269\\u54c1"),
        u("\\u6c34\\u679c"),
        u("\\u98df\\u7269"),
        u("\\u8eab\\u4f53"),
        u("\\u8fd0\\u52a8"),
        u("\\u505a\\u8fd0\\u52a8"),
        u("\\u5176\\u4ed6"),
        u("\\u5f62\\u5bb9\\u8bcd"),
        u("\\u52a8\\u8bcd\\u4ee5\\u53ca\\u52a8\\u8bcd\\u8bcd\\u7ec4"),
    ]
    sentence_titles = [
        u("\\u95ee\\u5019\\u76f8\\u5173"),
        u("\\u59d3\\u540d\\u76f8\\u5173"),
        u("\\u65f6\\u95f4\\u76f8\\u5173"),
        u("\\u6570\\u91cf\\u76f8\\u5173"),
        u("\\u51fa\\u884c\\u76f8\\u5173"),
        u("\\u7269\\u54c1\\u3001\\u52a8\\u7269\\u76f8\\u5173"),
        u("\\u559c\\u597d\\u76f8\\u5173"),
        u("\\u770b\\u89c1\\u76f8\\u5173"),
        u("\\u989c\\u8272\\u76f8\\u5173"),
        u("\\u4eba\\u7269\\u4ecb\\u7ecd\\u76f8\\u5173"),
        u("\\u505a\\u4e8b\\u60c5\\u76f8\\u5173"),
        u("\\u5b66\\u6821\\u76f8\\u5173"),
        u("\\u8282\\u65e5\\u76f8\\u5173"),
        u("\\u80fd\\u529b\\u76f8\\u5173"),
        u("\\u5176\\u4ed6"),
    ]
    faststory_titles = [
        "Please go to bed early.",
        "I go to school on an elephant today",
        "A super player",
        "A nice week",
        "Sunday is a big day",
        "A fun race",
    ]

    stories: list[dict[str, str]] = []
    for title in faststory_titles:
        try:
            start = doc_lines.index(title)
        except ValueError:
            stories.append({"title_en": title, "content": ""})
            continue
        content_lines: list[str] = []
        for ln in doc_lines[start + 1 :]:
            if ln in faststory_titles:
                break
            content_lines.append(ln)
        stories.append({"title_en": title, "content": "\n".join(content_lines).strip()})

    vocab_json = {
        "type": "VOCAB",
        "count": 17,
        "items": [{"index": i + 1, "title_zh": t, "title_en": ""} for i, t in enumerate(vocab_titles)],
    }
    sentence_json = {
        "type": "SENTENCE",
        "count": 15,
        "items": [{"index": i + 1, "title_zh": t, "title_en": ""} for i, t in enumerate(sentence_titles)],
    }
    faststory_json = {
        "type": "FASTSTORY",
        "count": 6,
        "items": [
            {"index": i + 1, "title_zh": s["title_en"], "title_en": s["title_en"], "content": s["content"]}
            for i, s in enumerate(stories)
        ],
    }

    (structured_dir / "vocab_17.json").write_text(json.dumps(vocab_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (structured_dir / "sentence_15.json").write_text(
        json.dumps(sentence_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (structured_dir / "faststory_6.json").write_text(
        json.dumps(faststory_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (structured_dir / "vocab_17.txt").write_text(
        "\n".join([f"C{it['index']:02d} {it['title_zh']}" for it in vocab_json["items"]]), encoding="utf-8"
    )
    (structured_dir / "sentence_15.txt").write_text(
        "\n".join([f"S{it['index']:02d} {it['title_zh']}" for it in sentence_json["items"]]), encoding="utf-8"
    )
    (structured_dir / "faststory_6.txt").write_text(
        "\n\n".join([f"P{it['index']:02d} {it['title_en']}\n{it['content']}" for it in faststory_json["items"]]),
        encoding="utf-8",
    )

    cn_di = u("\\u7b2c")
    cn_lei = u("\\u7c7b")
    cn_pian = u("\\u7bc7")
    cn_juzi = u("\\u53e5\\u5b50")
    mappings = {
        "VOCAB": {"max_index": 17, "items": {}},
        "SENTENCE": {"max_index": 15, "items": {}},
        "FASTSTORY": {"max_index": 6, "items": {}},
        "GLOBAL_SYNONYMS": {
            "VOCAB": [u("\\u8bcd\\u6c47"), u("\\u5355\\u8bcd"), u("\\u8bcd\\u7ec4")],
            "SENTENCE": [u("\\u53e5\\u5b50"), u("\\u53e5\\u578b"), u("\\u53e5\\u578b\\u79ef\\u7d2f")],
            "FASTSTORY": [u("\\u5feb\\u5634"), u("\\u9605\\u8bfb"), u("\\u5c0f\\u77ed\\u6587")],
        },
    }
    for it in vocab_json["items"]:
        i = it["index"]
        t = it["title_zh"]
        mappings["VOCAB"]["items"][str(i)] = {
            "title_zh": t,
            "title_en": "",
            "synonyms": [t, f"{cn_di}{i}{cn_lei}", f"{i}{cn_lei}"],
        }
    for it in sentence_json["items"]:
        i = it["index"]
        t = it["title_zh"]
        mappings["SENTENCE"]["items"][str(i)] = {
            "title_zh": t,
            "title_en": "",
            "synonyms": [t, f"{cn_di}{i}{cn_lei}", f"{i}{cn_lei}", f"{cn_juzi}{i}"],
        }
    for it in faststory_json["items"]:
        i = it["index"]
        t = it["title_en"]
        mappings["FASTSTORY"]["items"][str(i)] = {
            "title_zh": t,
            "title_en": t,
            "synonyms": [t, t.lower(), f"{cn_di}{i}{cn_pian}", f"{i}{cn_pian}"],
        }

    (structured_dir / "mappings_seed_from_originalText.json").write_text(
        json.dumps(mappings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    config_mappings_path.write_text(json.dumps(mappings, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"PDF source: {pdf_txt.name}")
    print(f"DOCX source: {doc_txt.name}")
    print("Wrote: vocab_17.json / sentence_15.json / faststory_6.json")
    print(f"Updated mappings: {config_mappings_path}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    src_dir = root / "originalText"
    converted_dir = src_dir / "converted"
    structured_dir = src_dir / "structured"
    config_mappings_path = root / "HomeworkVault" / "Config" / "mappings.json"

    extract_sources(src_dir, converted_dir)
    build_structured(converted_dir, structured_dir, config_mappings_path)


if __name__ == "__main__":
    main()
