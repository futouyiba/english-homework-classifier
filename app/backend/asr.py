from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import RuntimeSettings


@dataclass
class AsrResult:
    engine: str
    text: str
    lang: str
    segments: list[dict[str, Any]]
    duration_sec: float


_WHISPER_MODEL_CACHE: dict[str, Any] = {}


def _duration_from_segments(segments: list[dict[str, Any]]) -> float:
    if not segments:
        return 0.0
    return max(float(seg.get("t1", 0.0) or 0.0) for seg in segments)


def _normalize_segments(raw_segments: Any) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    if not raw_segments:
        return segments

    def _pick(seg_obj: Any, *keys: str, default: Any = None) -> Any:
        for key in keys:
            if isinstance(seg_obj, dict) and key in seg_obj:
                return seg_obj[key]
            if hasattr(seg_obj, key):
                return getattr(seg_obj, key)
        return default

    for seg in raw_segments:
        t0 = float(_pick(seg, "start", "t0", default=0.0) or 0.0)
        t1 = float(_pick(seg, "end", "t1", default=0.0) or 0.0)
        text = str(_pick(seg, "text", default="") or "").strip()
        segments.append({"t0": t0, "t1": t1, "text": text})
    return segments


def _asr_whisper_local(audio_path: Path, settings: RuntimeSettings) -> AsrResult:
    try:
        import whisper  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "ASR_ENGINE=whisper_local 但未安装 openai-whisper。请安装依赖或切换 ASR_ENGINE=stub/openai_api。"
        ) from exc

    model = _WHISPER_MODEL_CACHE.get(settings.whisper_model)
    if model is None:
        model = whisper.load_model(settings.whisper_model)
        _WHISPER_MODEL_CACHE[settings.whisper_model] = model

    data = model.transcribe(
        str(audio_path),
        language=settings.whisper_language or None,
        verbose=False,
        task="transcribe",
        fp16=False,
    )
    text = str(data.get("text", "")).strip()
    segments = _normalize_segments(data.get("segments", []))
    lang = str(data.get("language", settings.whisper_language)).strip() or settings.whisper_language
    duration_sec = _duration_from_segments(segments)
    return AsrResult(engine="whisper_local", text=text, lang=lang, segments=segments, duration_sec=duration_sec)


def _asr_openai_api(audio_path: Path, settings: RuntimeSettings) -> AsrResult:
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("ASR_ENGINE=openai_api 但未安装 openai SDK。") from exc

    if not settings.openai_api_key:
        raise RuntimeError("ASR_ENGINE=openai_api 需要设置 OPENAI_API_KEY。")

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    with audio_path.open("rb") as file_obj:
        response = client.audio.transcriptions.create(
            model=settings.openai_model,
            file=file_obj,
            response_format="verbose_json",
            language=settings.whisper_language,
        )

    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    elif isinstance(response, dict):
        payload = response
    else:
        payload = {"text": str(response)}

    text = str(payload.get("text", "")).strip()
    lang = str(payload.get("language", settings.whisper_language)).strip() or settings.whisper_language
    segments = _normalize_segments(payload.get("segments", []))
    duration_sec = float(payload.get("duration", 0.0) or _duration_from_segments(segments))
    return AsrResult(engine="openai_api", text=text, lang=lang, segments=segments, duration_sec=duration_sec)


def _asr_stub(audio_path: Path) -> AsrResult:
    text = audio_path.stem
    return AsrResult(
        engine="stub",
        text=text,
        lang="zh",
        segments=[{"t0": 0.0, "t1": 0.0, "text": text}],
        duration_sec=0.0,
    )


def transcribe_audio(audio_path: Path, settings: RuntimeSettings) -> AsrResult:
    if settings.asr_engine == "whisper_local":
        return _asr_whisper_local(audio_path, settings)
    if settings.asr_engine == "openai_api":
        return _asr_openai_api(audio_path, settings)
    return _asr_stub(audio_path)


def tagging_text(asr_result: AsrResult, window_sec: int) -> str:
    if window_sec <= 0:
        return asr_result.text.strip()
    if not asr_result.segments:
        return asr_result.text.strip()

    snippets: list[str] = []
    for seg in asr_result.segments:
        t0 = float(seg.get("t0", 0.0) or 0.0)
        t1 = float(seg.get("t1", 0.0) or 0.0)
        if t0 <= window_sec:
            text = str(seg.get("text", "")).strip()
            if text:
                snippets.append(text)
        if t1 >= window_sec:
            break

    head_text = " ".join(snippets).strip()
    return head_text or asr_result.text.strip()


def _has_ffmpeg() -> bool:
    return bool(shutil_which("ffmpeg"))


def shutil_which(binary: str) -> str | None:
    # Local wrapper to keep imports minimal and explicit.
    from shutil import which

    return which(binary)


def extract_head_clip(audio_path: Path, window_sec: int) -> Path | None:
    if window_sec <= 0 or not _has_ffmpeg():
        return None

    fd, tmp_path = tempfile.mkstemp(prefix="asr_head_", suffix=".wav")
    os.close(fd)
    out = Path(tmp_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-t",
        str(window_sec),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(out),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        return None
    return out


def transcribe_with_head_window(audio_path: Path, settings: RuntimeSettings) -> tuple[AsrResult, str]:
    full = transcribe_audio(audio_path, settings)
    head_text = tagging_text(full, settings.asr_tag_window_sec)

    clip_path = extract_head_clip(audio_path, settings.asr_tag_window_sec)
    if clip_path is None:
        return full, head_text

    try:
        head_result = transcribe_audio(clip_path, settings)
        if head_result.text.strip():
            head_text = head_result.text.strip()
    finally:
        clip_path.unlink(missing_ok=True)

    return full, head_text


def transcribe_for_scope(
    audio_path: Path,
    settings: RuntimeSettings,
    scope: str = "full",
) -> tuple[AsrResult, str, dict[str, Any]]:
    normalized_scope = scope.strip().lower()
    if normalized_scope not in {"full", "head", "hybrid"}:
        normalized_scope = "full"

    t_start = time.perf_counter()
    timing_ms: dict[str, float] = {}
    used_head_clip = False
    fallback_to_full = False
    clip_eligible = settings.asr_engine != "stub"

    if normalized_scope == "hybrid":
        t_full_start = time.perf_counter()
        full = transcribe_audio(audio_path, settings)
        timing_ms["asr_full"] = round((time.perf_counter() - t_full_start) * 1000, 2)
        head_text = tagging_text(full, settings.asr_tag_window_sec)

        if clip_eligible:
            t_clip_start = time.perf_counter()
            clip_path = extract_head_clip(audio_path, settings.asr_tag_window_sec)
            timing_ms["head_clip"] = round((time.perf_counter() - t_clip_start) * 1000, 2)
            used_head_clip = clip_path is not None
            if clip_path is not None:
                try:
                    t_head_start = time.perf_counter()
                    head = transcribe_audio(clip_path, settings)
                    timing_ms["asr_head"] = round((time.perf_counter() - t_head_start) * 1000, 2)
                    if head.text.strip():
                        head_text = head.text.strip()
                finally:
                    clip_path.unlink(missing_ok=True)
        else:
            timing_ms["head_clip"] = 0.0

        timing_ms["total"] = round((time.perf_counter() - t_start) * 1000, 2)
        return full, head_text, {
            "scope": normalized_scope,
            "used_head_clip": used_head_clip,
            "fallback_to_full": fallback_to_full,
            "timing_ms": timing_ms,
        }

    if normalized_scope == "head":
        if clip_eligible:
            t_clip_start = time.perf_counter()
            clip_path = extract_head_clip(audio_path, settings.asr_tag_window_sec)
            timing_ms["head_clip"] = round((time.perf_counter() - t_clip_start) * 1000, 2)
            used_head_clip = clip_path is not None

            if clip_path is not None:
                try:
                    t_asr_start = time.perf_counter()
                    head = transcribe_audio(clip_path, settings)
                    timing_ms["asr"] = round((time.perf_counter() - t_asr_start) * 1000, 2)
                    timing_ms["total"] = round((time.perf_counter() - t_start) * 1000, 2)
                    return head, head.text.strip(), {
                        "scope": normalized_scope,
                        "used_head_clip": used_head_clip,
                        "fallback_to_full": fallback_to_full,
                        "timing_ms": timing_ms,
                    }
                finally:
                    clip_path.unlink(missing_ok=True)

        timing_ms["head_clip"] = timing_ms.get("head_clip", 0.0)
        fallback_to_full = True

    t_asr_start = time.perf_counter()
    full = transcribe_audio(audio_path, settings)
    timing_ms["asr"] = round((time.perf_counter() - t_asr_start) * 1000, 2)
    head_text = tagging_text(full, settings.asr_tag_window_sec)
    timing_ms["total"] = round((time.perf_counter() - t_start) * 1000, 2)
    return full, head_text, {
        "scope": normalized_scope,
        "used_head_clip": used_head_clip,
        "fallback_to_full": fallback_to_full,
        "timing_ms": timing_ms,
    }
