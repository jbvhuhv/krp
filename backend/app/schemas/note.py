from pydantic import BaseModel

from app.core.constants import NOTE_STATUS
from app.schemas.common import UtcDateTime


class NoteCreate(BaseModel):
    title: str
    content: str
    format: str = "markdown"
    tags: list[str] = []


class NoteOut(BaseModel):
    id: str
    title: str
    format: str
    tags: list[str] = []
    upload_time: UtcDateTime
    task_id: str | None = None
    content: str | None = None
    status: str = NOTE_STATUS["PENDING"]
    nodes_count: int = 0
    edges_count: int = 0
    error_message: str | None = None
    processed_time: UtcDateTime | None = None


class NoteList(BaseModel):
    items: list[NoteOut]
    total: int
