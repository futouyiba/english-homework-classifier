from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ItemType(str, Enum):
    VOCAB = "VOCAB"
    SENTENCE = "SENTENCE"
    FASTSTORY = "FASTSTORY"


class ProcessAudioRequest(BaseModel):
    path: str = Field(..., description="Absolute or project-relative file path")


class RelabelRequest(BaseModel):
    id: str
    type: ItemType
    index: int = Field(..., ge=1)
    title_zh: str = ""
    title_en: str = ""


class TeacherParseRequest(BaseModel):
    text: str


class DailyBuildRequest(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    teacher_cmd: str
    needs: dict[str, list[int]]


class MappingsUpdateRequest(BaseModel):
    payload: dict[str, Any]
