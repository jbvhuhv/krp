import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


class ReflectionRecord(Base):
    __tablename__ = "reflection_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    mastery_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    concept_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    logic_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    example_reasonableness: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    node_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReflectionSchedule(Base):
    __tablename__ = "reflection_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True, nullable=False)
    frequency: Mapped[str] = mapped_column(String(32), default="daily")
    time_window: Mapped[str] = mapped_column(String(64), default="20:00-21:00")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
