import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import NOTE_STATUS
from app.models.user import Base


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(32), default="markdown")
    tags: Mapped[str] = mapped_column(Text, default="")
    # 上传时用户可指定学科；为空则由抽取模型自行判断。
    # 存在的意义：LLM 认不出的专业课前，用户自己最清楚这份笔记属于哪门课，
    # 否则知识图谱里会堆出一批「未分类」节点，学科筛选也筛不出来。
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    upload_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 知识抽取状态：pending / processing / success / empty / failed
    status: Mapped[str] = mapped_column(String(16), default=NOTE_STATUS["PENDING"])
    nodes_count: Mapped[int] = mapped_column(Integer, default=0)
    edges_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
