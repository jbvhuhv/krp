import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    # 评分时的薄弱点与推荐资源：JSON 数组的字符串形式。
    # 不落库的话，用户重新打开同一道题只能看到分数，看不到当初的分析。
    weak_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    resources: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 出题依据：为什么今天问这道题（弱信号解释），以及题目是否由模板兜底生成。
    # 不落库的话，前端只能干巴巴地甩一道题，用户不知道它和哪篇笔记/哪次问答有关。
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # 掌握度溯源：评分当下就把「改前 / 改后 / 本次新观测权重」记下来。
    # 只在事后回放公式会漂移（图谱初值与历史都是可变的），记账才是可解释的。
    mastery_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    mastery_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    mastery_weight: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NodeView(Base):
    """知识点被打开查看的埋点。

    掌握度过去只有一个输入——反思答题，于是「不答题 → 图谱永远不动」，
    反思也就每天出同一批题。查看行为是最轻的行为信号：它不改掌握度，
    只说明用户最近在关注这块内容，用于调整出题顺序。
    """

    __tablename__ = "node_views"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class NodeMasteryOverride(Base):
    """演示模式下的掌握度覆盖层。

    内置只读图谱（无 Neo4j 部署）不能写回 jsonl，但「答题 → 掌握度上升 →
    第二天换一批题」是反思闭环的核心。把答题结果落到这张表里，读图谱时合并，
    既能保持演示图谱本身只读，又不会让用户答完题后一切照旧。
    """

    __tablename__ = "node_mastery_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "node_id", name="uq_node_mastery_override"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    mastery: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReflectionSchedule(Base):
    __tablename__ = "reflection_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True, nullable=False)
    frequency: Mapped[str] = mapped_column(String(32), default="daily")
    time_window: Mapped[str] = mapped_column(String(64), default="20:00-21:00")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
