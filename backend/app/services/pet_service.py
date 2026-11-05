import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import (
    PET_EXP_BASE,
    PET_EXP_STEP,
    PET_GROWTH_CONCAVITY,
    PET_GROWTH_PER_NODE,
    PET_KNOWLEDGE_FOR_FULL,
    PET_KNOWLEDGE_PER_FRUIT,
    PET_MAX_TREE_FRUITS,
)
from app.core.logger import get_logger
from app.models.pet import Pet, PetMessage

logger = get_logger(__name__)

# 可选的宠物物种（前端 PetAvatar.vue 按此 key 渲染不同造型）
SPECIES = ["spirit", "jelly", "fox", "cat", "rabbit", "bear", "dragon", "bird"]
# 主色调（hex，前端用于上色）
COLORS = [
    "#22d3ee",
    "#a855f7",
    "#f472b6",
    "#34d399",
    "#fb923c",
    "#60a5fa",
    "#fbbf24",
    "#f87171",
]
# 名字：前缀 + 物种词根组合，保证名字与外观贴合
NAME_PREFIX = ["小", "团", "糯", "星", "糖", "云", "露", "雪", "月", "光", "花", "棉", "巧", "莓", "桃", "泡", "闪", "萌"]
SPECIES_ROOT = {
    "spirit": "灵",
    "jelly": "泡",
    "fox": "狐",
    "cat": "咪",
    "rabbit": "兔",
    "bear": "熊",
    "dragon": "龙",
    "bird": "啾",
}
# 性格标签
PERSONALITIES = ["好奇", "温柔", "活泼", "害羞", "勇敢", "贪吃", "爱睡", "机灵", "安静", "话痨", "聪明", "黏人"]

# 宠物语音音色预设（热门声音）。engine="browser" 表示由浏览器 Web Speech API 合成；
# 未来接入后端 TTS 时改为 engine="backend" 并补 backend_voice_id，数据结构不变。
VOICE_PRESETS = {
    "cute_girl": {"name": "可爱少女", "engine": "browser", "backend_voice_id": None},
    "gentle_woman": {"name": "温柔女声", "engine": "browser", "backend_voice_id": None},
    "lively_kid": {"name": "活泼童声", "engine": "browser", "backend_voice_id": None},
    "magnetic_man": {"name": "磁性男声", "engine": "browser", "backend_voice_id": None},
    "calm_narrator": {"name": "沉稳旁白", "engine": "browser", "backend_voice_id": None},
}


# 成长数学模型的常量统一收敛到 app.core.constants，此处仅做模块级别名，
# 保证既有引用（pet_service.KNOWLEDGE_PER_FRUIT 等）继续可用，且避免双份定义漂移。
KNOWLEDGE_PER_FRUIT = PET_KNOWLEDGE_PER_FRUIT
MAX_TREE_FRUITS = PET_MAX_TREE_FRUITS
KNOWLEDGE_FOR_FULL = PET_KNOWLEDGE_FOR_FULL
GROWTH_CONCAVITY = PET_GROWTH_CONCAVITY
GROWTH_PER_NODE = PET_GROWTH_PER_NODE


def growth_from_nodes(total_nodes: float) -> float:
    """由知识点总数换算树木成长进度（0-100），边际递减。

    性质：在 n∈[0,80] 上严格单调递增、严格凹（边际递减）、双射可逆，
    端点 growth_from_nodes(0)=0、growth_from_nodes(80)=100。
    """
    u = min(1.0, max(0.0, total_nodes / KNOWLEDGE_FOR_FULL))
    return 100.0 * (1.0 - (1.0 - u) ** GROWTH_CONCAVITY)


def _nodes_from_growth(growth: float) -> float:
    """成长进度的反函数：把当前进度折算成等效知识点数，用于增量累加。

    与 growth_from_nodes 互为逆映射（误差 <1e-6），保证「反解-累加-正映射」
    的增量更新幂等、不丢精度。
    """
    g = min(1.0, max(0.0, growth / 100.0))
    return KNOWLEDGE_FOR_FULL * (1.0 - (1.0 - g) ** (1.0 / GROWTH_CONCAVITY))


def exp_max(level: int) -> int:
    """升到下一级所需经验：线性递增（base + step*(level-1)）。"""
    lv = max(1, int(level))
    return PET_EXP_BASE + PET_EXP_STEP * (lv - 1)


# 每投喂一颗果实获得的经验值
FEED_EXP_GAIN = 10


def derive_growth(total_nodes: int, consumed_growth: float) -> tuple[float, int]:
    """由知识点总数唯一派生「当前轮进度」与「待收割轮数」。

    - 每满 KNOWLEDGE_FOR_FULL 个知识点结算为一个完整成长轮次（+100 成长值）；
    - ``consumed_growth`` 记录已收割掉的成长值（每次收割 +100），
      已收割轮数 = consumed_growth // 100；
    - 待收割轮数 = 已满额轮数 - 已收割轮数（不小于 0），
      保证同一批知识不会重复成熟、也不会因一次性导入而丢失溢出部分。

    返回 (progress, ready_cycles)：
    - progress ∈ [0,100) 为当前未完成轮的成长进度；
    - ready_cycles ≥ 0 为可立即收割的成熟轮次数。
    """
    total = max(0, int(total_nodes))
    consumed_cycles = int(max(0.0, consumed_growth) // 100)
    earned_cycles = total // KNOWLEDGE_FOR_FULL
    progress = growth_from_nodes(total % KNOWLEDGE_FOR_FULL)
    return progress, max(0, earned_cycles - consumed_cycles)

# 成就奖杯：按累计收取果实总数分 12 档（星火 → 永恒），阈值只增，取最高档为当前星阶
MEDAL_TIERS = [
    {"id": "novice", "name": "星火", "threshold": 3},
    {"id": "sprout", "name": "初芒", "threshold": 9},
    {"id": "diligent", "name": "新星", "threshold": 18},
    {"id": "achiever", "name": "领航", "threshold": 27},
    {"id": "scholar", "name": "先驱", "threshold": 39},
    {"id": "adept", "name": "智核", "threshold": 54},
    {"id": "sage", "name": "光耀", "threshold": 72},
    {"id": "master", "name": "星环", "threshold": 93},
    {"id": "grandmaster", "name": "超维", "threshold": 117},
    {"id": "luminary", "name": "主宰", "threshold": 150},
    {"id": "titan", "name": "创世", "threshold": 210},
    {"id": "legend", "name": "永恒", "threshold": 300},
]


def generate_pet_identity(seed_input: str) -> dict:
    """由输入稳定派生一只独特宠物的身份，保证同一用户始终同一只。"""
    digest = hashlib.sha256(seed_input.encode("utf-8")).digest()
    species = SPECIES[digest[0] % len(SPECIES)]
    color = COLORS[digest[1] % len(COLORS)]
    personality = PERSONALITIES[digest[2] % len(PERSONALITIES)]
    name = NAME_PREFIX[digest[3] % len(NAME_PREFIX)] + SPECIES_ROOT[species]
    seed = int.from_bytes(digest[5:9], "big")
    return {
        "species": species,
        "color": color,
        "personality": personality,
        "name": name,
        "seed": seed,
    }


async def get_or_create_pet(db: AsyncSession, user_id: str) -> Pet:
    """获取用户宠物；不存在则创建，存量宠物缺身份则补生成。"""
    result = await db.execute(select(Pet).where(Pet.user_id == user_id))
    pet = result.scalar_one_or_none()
    if pet is None:
        pet = Pet(user_id=user_id, **generate_pet_identity(user_id))
        db.add(pet)
        await db.commit()
        await db.refresh(pet)
        return pet

    if not pet.species or not pet.name:
        identity = generate_pet_identity(user_id)
        for key, value in identity.items():
            setattr(pet, key, value)
        await db.commit()
        await db.refresh(pet)
    return pet


async def create_pet_for_user(db: AsyncSession, user_id: str) -> Pet:
    """注册时为新用户创建一只独特宠物。"""
    return await get_or_create_pet(db, user_id)



def compute_medals(total_harvested: int) -> list[dict]:
    """按累计收取果实总数计算各档成就奖杯的解锁状态。"""
    total = max(0, total_harvested)
    medals = [
        {
            "id": tier["id"],
            "name": tier["name"],
            "threshold": tier["threshold"],
            "unlocked": total >= tier["threshold"],
        }
        for tier in MEDAL_TIERS
    ]
    return medals


def current_medal_id(total_harvested: int) -> str | None:
    """当前已解锁的最高档成就奖杯 id；一档未解锁时返回 None。"""
    total = max(0, total_harvested)
    unlocked = [tier["id"] for tier in MEDAL_TIERS if total >= tier["threshold"]]
    return unlocked[-1] if unlocked else None


def next_medal(total_harvested: int) -> dict | None:
    """下一个待解锁的成就奖杯档位；全部解锁后返回 None。"""
    total = max(0, total_harvested)
    for tier in MEDAL_TIERS:
        if total < tier["threshold"]:
            return tier
    return None


def compute_pending_growth(total_nodes: int, consumed_growth: float) -> float:
    """由知识点总数与已消耗成长值推算当前应显示的树木成长进度（0-100）。

    成长曲线为边际递减的凹函数：每满 80 个知识点结算一个「成长轮次」（+100），
    轮次内按凹曲线递增；已收取果实对应的成长值会被扣除，
    避免同一批知识被反复结算成新果实。
    """
    total = max(0, int(total_nodes))
    full_cycles, remainder = divmod(total, KNOWLEDGE_FOR_FULL)
    raw = full_cycles * 100.0 + growth_from_nodes(remainder)
    return min(100.0, max(0.0, raw - max(0.0, consumed_growth)))


async def apply_knowledge_growth(db: AsyncSession, user_id: str, nodes_count: int) -> Pet | None:
    """知识输入驱动树木成长：新增知识点按边际递减曲线折算为成长值。

    以「知识点总数」为唯一事实来源，把树的状态拆成两个可无损累加的量：
    - ``tree_growth``：当前未完成轮的进度，等于 growth_from_nodes(节点数 % 80)；
    - ``growth_cycles``：累计已满额的轮次数，等于 节点数 // 80（只增不减）。

    由 (growth_cycles, tree_growth) 可精确反解出等效知识点总数
    ``growth_cycles*80 + _nodes_from_growth(tree_growth)``，因此一次性导入任意
    数量的知识点都不会丢失溢出部分（溢出自动进位为新的成长轮次）。
    """
    if nodes_count <= 0:
        return None
    pet = await get_or_create_pet(db, user_id)
    before = pet.tree_growth
    equivalent_nodes = (pet.growth_cycles or 0) * KNOWLEDGE_FOR_FULL + _nodes_from_growth(
        pet.tree_growth
    )
    total_nodes = equivalent_nodes + nodes_count
    pet.growth_cycles = int(total_nodes // KNOWLEDGE_FOR_FULL)
    pet.tree_growth = growth_from_nodes(total_nodes % KNOWLEDGE_FOR_FULL)
    await db.commit()
    await db.refresh(pet)
    logger.info(
        "知识驱动成长 user_id=%s nodes=%d growth=%.1f->%.1f cycles=%d",
        user_id,
        nodes_count,
        before,
        pet.tree_growth,
        pet.growth_cycles,
    )
    # 学到新知识 = 一次正向互动：提升亲密度、切换为自豪情绪
    apply_event(pet, "study")
    await db.commit()
    await db.refresh(pet)
    return pet


# ============================ 情感状态机 ============================
# 设计目标：让宠物拥有随时间演化、随互动变化的内在情感。
# - 事件驱动：投喂/收割/学习/对话分别切换到对应情绪并提升亲密度；
# - 时间衰减：长期冷落会变为孤单/疲惫，亲密度轻微回落（有下限，不惩罚过度）；
# - 连续打卡：按自然日累计 streak，形成正反馈的坚持动机。

# 全部可用情绪（前端据此切换表情/动画）
MOODS = ["happy", "excited", "content", "curious", "proud", "lonely", "tired"]

# 各互动事件触发的情绪
EVENT_MOOD = {
    "feed": "happy",
    "harvest": "excited",
    "study": "proud",
    "chat": "content",
    "greet": "curious",
}

# 各事件提供的亲密度增量
BOND_GAIN = {"feed": 2, "harvest": 5, "study": 3, "chat": 1, "greet": 0}
BOND_MAX = 100
# 冷落衰减：每多闲置一天扣 1 点，最低不为负
BOND_DECAY_PER_DAY = 1

# 情绪衰减阈值（小时）
LONELY_AFTER_HOURS = 24
TIRED_AFTER_HOURS = 72

# 亲密度分档（展示用）
BOND_LEVELS = [
    (0, "初识"),
    (20, "熟悉"),
    (40, "亲密"),
    (65, "羁绊"),
    (85, "灵魂伴侣"),
]


def now_utc() -> datetime:
    """业务时间统一使用 naive UTC（与 SQLite 存储口径一致）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_local(dt: datetime) -> datetime:
    """把 naive UTC 时间换算为用户本地时间（用于问候时段与日界判断）。"""
    return dt + timedelta(hours=settings.TIMEZONE_OFFSET_HOURS)


def apply_event(pet: Pet, event: str, now: datetime | None = None) -> None:
    """应用一次互动事件：更新情绪、亲密度与连续打卡天数（原地修改 pet）。"""
    now = now or now_utc()
    gain = BOND_GAIN.get(event, 0)
    pet.bond = min(BOND_MAX, max(0, int(pet.bond or 0)) + gain)
    pet.mood = EVENT_MOOD.get(event, pet.mood or "content")
    pet.last_interaction = now

    today = _to_local(now).date()
    if pet.last_active_date == today:
        pass
    elif pet.last_active_date == today - timedelta(days=1):
        pet.streak_days = (pet.streak_days or 0) + 1
    else:
        pet.streak_days = 1
    pet.last_active_date = today


def _idle_hours(pet: Pet, now: datetime) -> float | None:
    if pet.last_interaction is None:
        return None
    return max(0.0, (now - pet.last_interaction).total_seconds() / 3600.0)


def compute_mood(pet: Pet, now: datetime | None = None) -> str:
    """结合最近互动时间推断当前情绪：久未互动则孤单/疲惫，否则取记录的情绪。"""
    now = now or now_utc()
    idle = _idle_hours(pet, now)
    if idle is not None:
        if idle >= TIRED_AFTER_HOURS:
            return "tired"
        if idle >= LONELY_AFTER_HOURS:
            return "lonely"
    return pet.mood or "content"


def effective_bond(pet: Pet, now: datetime | None = None) -> int:
    """亲密度展示值：在存储值基础上按闲置天数轻微衰减（不低于 0）。"""
    now = now or now_utc()
    base = max(0, int(pet.bond or 0))
    idle_days = 0
    if pet.last_interaction is not None:
        idle_days = int(max(0.0, (now - pet.last_interaction).total_seconds()) // 86400)
    decay = max(0, idle_days - 1) * BOND_DECAY_PER_DAY
    return max(0, base - decay)


def bond_level(bond: int) -> str:
    """把亲密度数值映射为分档名称。"""
    level = BOND_LEVELS[0][1]
    for threshold, name in BOND_LEVELS:
        if bond >= threshold:
            level = name
    return level

# ============================ 对话记忆 ============================
# 多轮上下文的轮数上限（1 轮 = 主人 + 宠物各一条）
PET_HISTORY_TURNS = 6
# 每个用户最多保留的历史消息条数，超出后裁剪最旧的，避免无限增长
PET_HISTORY_MAX_MESSAGES = 200


async def load_recent_messages(
    db: AsyncSession, user_id: str, limit: int = PET_HISTORY_TURNS
) -> list[dict]:
    """读取最近若干轮对话，按时间正序返回，供 Prompt 拼接上下文。"""
    result = await db.execute(
        select(PetMessage)
        .where(PetMessage.user_id == user_id)
        .order_by(PetMessage.created_at.desc())
        .limit(max(0, limit) * 2)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return [{"role": row.role, "content": row.content} for row in rows]


async def save_chat_exchange(
    db: AsyncSession, user_id: str, user_message: str, assistant_message: str
) -> None:
    """保存一轮完整对话（主人 + 宠物），并裁剪过旧的历史。"""
    if not assistant_message:
        return
    db.add(PetMessage(user_id=user_id, role="user", content=user_message))
    db.add(PetMessage(user_id=user_id, role="assistant", content=assistant_message))
    await db.commit()

    # 轻量裁剪：仅保留最近 PET_HISTORY_MAX_MESSAGES 条
    result = await db.execute(
        select(PetMessage.id)
        .where(PetMessage.user_id == user_id)
        .order_by(PetMessage.created_at.desc())
        .offset(PET_HISTORY_MAX_MESSAGES)
    )
    stale_ids = [row for row in result.scalars().all()]
    if stale_ids:
        await db.execute(
            PetMessage.__table__.delete().where(PetMessage.id.in_(stale_ids))
        )
        await db.commit()

# ============================ 主动关怀 ============================
# 依恋理论：宠物在主人久未出现或每日首次归来时主动开口，
# 能显著增强「被需要」的陪伴感。每日最多一次，避免打扰。


def build_care_message(
    pet: Pet, now: datetime | None = None, total_nodes: int | None = None
) -> str:
    """根据情绪、连续打卡天数与时段生成一句个性化的主动问候。

    ``total_nodes`` 为 None 表示调用方不掌握知识点情况（如单元测试、旧调用点），
    此时不做「零知识」判断，保持原有按情绪/时段的文案。
    """
    now = now or now_utc()
    mood = compute_mood(pet, now)
    name = pet.name or "我"
    streak = pet.streak_days or 0

    # 还没有任何知识点时，不要说「树又长大了」这类与事实矛盾的话，
    # 而是给出下一步可执行的引导。
    if total_nodes is not None and total_nodes <= 0:
        return f"{name}还在等你教第一份知识呢～上传一篇笔记，我就能和知识树一起长大啦！"

    if mood == "tired":
        return f"主人～好久没见到你了，{name}有点想你了，快回来看看我嘛～"
    if mood == "lonely":
        return "主人是不是很忙呀？我还惦记着你上次教我的知识呢，等你回来～"
    if streak >= 7:
        return f"哇！主人已经连续 {streak} 天来找我啦，我们越来越有默契了！"
    if streak >= 3:
        return f"主人连续 {streak} 天来陪我，{name}超开心的！"

    hour = _to_local(now).hour
    if hour < 6:
        return "这么晚还在努力呀，主人要注意休息哦～"
    if hour < 12:
        return f"早安主人！{name}今天也想和你一起学点新东西～"
    if hour < 18:
        return "下午好呀主人，我们的知识树又悄悄长大了一点！"
    return "晚上好主人～今天有什么收获想跟我分享吗？"


def take_daily_care(
    pet: Pet, now: datetime | None = None, total_nodes: int = 0
) -> str | None:
    """每日首次访问时返回一句主动问候（并记录当天已问候），否则返回 None。"""
    now = now or now_utc()
    today = _to_local(now).date()
    if pet.last_care_date == today:
        return None
    pet.last_care_date = today
    return build_care_message(pet, now, total_nodes=total_nodes)
