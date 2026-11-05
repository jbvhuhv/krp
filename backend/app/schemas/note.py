from pydantic import BaseModel

from app.core.constants import NOTE_STATUS
from app.schemas.common import UtcDateTime


class NoteCreate(BaseModel):
    title: str
    content: str
    format: str = "markdown"
    tags: list[str] = []
    subject: str | None = None


class NoteUpdate(BaseModel):
    """笔记的可编辑字段。

    标题改的是「展示名」，同时会把对应图谱书根节点的名字一起改掉，
    否则书架里还是旧文件名，用户会以为没保存成功。
    """

    title: str | None = None
    subject: str | None = None


class NoteOut(BaseModel):
    id: str
    title: str
    format: str
    tags: list[str] = []
    subject: str | None = None
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
