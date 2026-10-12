import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import Base


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Pet(Base):
    __tablename__ = "pets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    exp: Mapped[int] = mapped_column(Integer, default=0)
    fruits: Mapped[int] = mapped_column(Integer, default=0)
    # 累计收取的果实总数（只增不减），用于奖牌激励，与余额 fruits 区分
    total_harvested: Mapped[int] = mapped_column(Integer, default=0)
    tree_growth: Mapped[float] = mapped_column(Float, default=0.0)
    # 累计已满额的成长轮次数（只增不减），等于「知识点总数 // 80」。
    # 与 tree_growth(当前轮进度) 一起构成成长的无损状态，支持一次性导入的溢出进位。
    growth_cycles: Mapped[int] = mapped_column(Integer, default=0)
    # 已被"收取果实"消耗掉的累计成长值，用于防止同一批知识被反复结算成新果实
    tree_growth_consumed: Mapped[float] = mapped_column(Float, default=0.0)
    # 独特宠物身份：由用户稳定派生，保证每个用户一只不同外观的宠物
    name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    species: Mapped[str | None] = mapped_column(String(24), nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    personality: Mapped[str | None] = mapped_column(String(24), nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 宠物语音音色预设 id（热门声音）。为空表示用户未主动配置，前端套用默认档。
    # 存 preset id 而非具体 voiceURI，未来切换后端 TTS 无需改结构。
    voice_preset: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # —— 情感状态机（由学习/投喂/收割/对话等事件驱动，含时间衰减）——
    # 当前情绪：happy/excited/content/curious/proud/lonely/tired 等
    mood: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 亲密度（0-100），随正向互动增长、随长期冷落轻微衰减
    bond: Mapped[int] = mapped_column(Integer, default=0)
    # 最近一次有效互动时间；用于推断孤单/疲惫等情绪
    last_interaction: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 连续互动天数（打卡 Streak）与最近一次互动日期
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 最近一次「主动关怀」问候的日期（每日最多一次，避免打扰）
    last_care_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class PetMessage(Base):
    """宠物对话记忆：保存主人与宠物的最近若干轮对话，供多轮上下文使用。"""

    __tablename__ = "pet_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    # 角色：user（主人）/ assistant（宠物）
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, index=True)
