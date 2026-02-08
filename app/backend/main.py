from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
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
