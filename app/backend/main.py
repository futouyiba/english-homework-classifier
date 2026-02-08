from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import INBOX_DIR, PROJECT_ROOT, ensure_bootstrap, load_runtime_settings
from .asr import transcribe_for_scope
from .schemas import (
    DailyBuildRequest,
    MappingsUpdateRequest,
    ProcessAudioRequest,
    RelabelRequest,
    TeacherParseRequest,
)
from .services import (
    build_daily_package,
    library_summary,
    library_takes,
    list_recent_items,
    load_mappings,
    parse_teacher_command,
    preview_tag_for_text,
    process_audio_file,
    relabel_item,
    save_mappings,
    scan_inbox,
)

app = FastAPI(title="Homework Audio Agent API", version="0.1.0")
FRONTEND_DIR = PROJECT_ROOT / "app" / "frontend"
VAULT_ROOT = (PROJECT_ROOT / "HomeworkVault").resolve()
STRUCTURED_DIR = (PROJECT_ROOT / "originalText" / "structured").resolve()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ensure_bootstrap()


if FRONTEND_DIR.exists():
    app.mount("/ui/static", StaticFiles(directory=str(FRONTEND_DIR)), name="ui-static")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/ui", include_in_schema=False)
def ui_page() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


@app.get("/api/health")
def health() -> dict[str, Any]:
    from datetime import datetime, timezone

    runtime = load_runtime_settings()
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "asr_engine": runtime.asr_engine,
        "asr_process_scope": runtime.asr_process_scope,
        "whisper_model": runtime.whisper_model,
        "asr_tag_window_sec": runtime.asr_tag_window_sec,
    }


@app.post("/api/inbox/upload")
async def inbox_upload(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    ensure_bootstrap()
    saved: list[dict[str, str]] = []
    for file in files:
        if not file.filename:
            continue
        target = INBOX_DIR / file.filename
        data = await file.read()
        target.write_bytes(data)
        saved.append({"name": file.filename, "path": str(target.relative_to(PROJECT_ROOT))})
    return {"saved": saved}


@app.post("/api/inbox/scan")
def inbox_scan() -> dict[str, int]:
    return scan_inbox()


@app.get("/api/inbox/items")
def inbox_items() -> list[dict[str, Any]]:
    return list_recent_items()


@app.post("/api/audio/process")
def audio_process(payload: ProcessAudioRequest) -> dict[str, Any]:
    try:
        return process_audio_file(payload.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"File not found: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/audio/relabel")
def audio_relabel(payload: RelabelRequest) -> dict[str, Any]:
    try:
        return relabel_item(
            item_id=payload.id,
            item_type=payload.type.value,
            index=payload.index,
            title_zh=payload.title_zh,
            title_en=payload.title_en,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/asr/test")
async def asr_test(
    file: UploadFile = File(...),
    tag_window_sec: int | None = Query(default=None, ge=1),
    scope: str = Query(default="full", pattern="^(full|head|hybrid)$"),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    runtime = load_runtime_settings()
    if tag_window_sec is not None:
        runtime = replace(runtime, asr_tag_window_sec=tag_window_sec)

    safe_name = Path(file.filename).name
    safe_name = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in safe_name)

    try:
        with tempfile.TemporaryDirectory(prefix="asr_test_") as tmp_dir:
            temp_path = Path(tmp_dir) / safe_name
            temp_path.write_bytes(await file.read())
            asr_result, head_text, debug = transcribe_for_scope(temp_path, runtime, scope=scope)
            tag_preview = preview_tag_for_text(head_text or asr_result.text)
            return {
                "engine": asr_result.engine,
                "lang": asr_result.lang,
                "duration_sec": asr_result.duration_sec,
                "scope": debug["scope"],
                "used_head_clip": debug["used_head_clip"],
                "fallback_to_full": debug["fallback_to_full"],
                "timing_ms": debug["timing_ms"],
                "asr_text": asr_result.text,
                "tag_window_text": head_text,
                "segments": asr_result.segments,
                "tag_preview": tag_preview,
            }
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _resolve_vault_file(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be project-relative")
    target = (PROJECT_ROOT / candidate).resolve()
    try:
        target.relative_to(PROJECT_ROOT.resolve())
        target.relative_to(VAULT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return target


def _resolve_structured_file(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be relative")
    target = (STRUCTURED_DIR / candidate).resolve()
    try:
        target.relative_to(STRUCTURED_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return target


@app.get("/api/file")
def get_file(path: str = Query(..., description="Project-relative file path")) -> FileResponse:
    target = _resolve_vault_file(path)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.get("/api/text")
def get_text(path: str = Query(..., description="Project-relative text path")) -> dict[str, str]:
    target = _resolve_vault_file(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        text = target.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read text file: {exc}") from exc
    return {"path": path, "text": text}


@app.post("/api/open-folder")
def open_folder(path: str = Query(..., description="Project-relative folder path")) -> dict[str, bool]:
    target = _resolve_vault_file(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", str(target)])
        else:
            raise HTTPException(status_code=400, detail="Open folder is only supported on Windows")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/structured/list")
def structured_list() -> dict[str, list[str]]:
    if not STRUCTURED_DIR.exists():
        return {"files": []}
    files = sorted([p.name for p in STRUCTURED_DIR.glob("*") if p.is_file()])
    return {"files": files}


@app.get("/api/structured/read")
def structured_read(path: str = Query(..., description="File name under originalText/structured")) -> dict[str, Any]:
    target = _resolve_structured_file(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if target.suffix.lower() == ".json":
        try:
            return {"path": path, "data": json.loads(target.read_text(encoding="utf-8"))}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    return {"path": path, "text": target.read_text(encoding="utf-8")}


@app.post("/api/config/apply-seed")
def config_apply_seed(
    seed_file: str = Query(default="mappings_seed_from_originalText.json", description="Seed JSON under structured dir"),
) -> dict[str, bool]:
    target = _resolve_structured_file(seed_file)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Seed file not found")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        save_mappings(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot apply seed: {exc}") from exc
    return {"ok": True}


@app.get("/api/library/summary")
def get_library_summary() -> list[dict[str, Any]]:
    return library_summary()


@app.get("/api/library/takes")
def get_library_takes(item_type: str = Query(..., alias="type"), index: int = Query(..., ge=1)) -> dict[str, Any]:
    try:
        return library_takes(item_type=item_type, index=index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/teacher/parse")
def teacher_parse(payload: TeacherParseRequest) -> dict[str, Any]:
    return parse_teacher_command(payload.text)


@app.post("/api/daily/build")
def daily_build(payload: DailyBuildRequest) -> dict[str, Any]:
    try:
        return build_daily_package(
            date_str=payload.date,
            teacher_cmd=payload.teacher_cmd,
            needs=payload.needs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/config/mappings")
def config_get() -> dict[str, Any]:
    return load_mappings()


@app.put("/api/config/mappings")
def config_put(payload: MappingsUpdateRequest) -> dict[str, bool]:
    try:
        save_mappings(payload.payload)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.backend.main:app", host="127.0.0.1", port=8000, reload=True)
