from pydantic import BaseModel, Field


class KnowledgeThread(BaseModel):
    """一条知识脉络（来自一份成功抽取的笔记）。"""

    note_id: str
    title: str
    nodes_count: int = 0
    edges_count: int = 0


class PetMedal(BaseModel):
    """一档奖牌（按累计收取果实总数解锁）。"""

    id: str
    name: str
    threshold: int
    unlocked: bool


class PetStatus(BaseModel):
    level: int
    exp: int
    exp_max: int
    fruits: int
    tree_growth: float
    tree_stage: str
    # 可立即收割的成熟轮次数（>0 表示树上有果实可收；支持一次性导入的溢出进位）
    harvestable_cycles: int = 0
    # 情感状态机：当前情绪、亲密度（衰减后展示值）与分档、连续互动天数
    mood: str = "content"
    bond: int = 0
    bond_level: str = "初识"
    streak_days: int = 0
    # 主动关怀：每日首次访问时由宠物主动说出的一句问候（当天已问候则为 None）
    greeting: str | None = None
    # 独特宠物身份
    name: str | None = None
    species: str | None = None
    color: str | None = None
    personality: str | None = None
    # 知识花园：知识点总数、树上果实（= 知识脉络）数量与列表
    knowledge_total: int = 0
    tree_fruits: int = 0
    threads: list[KnowledgeThread] = []
    # 奖牌激励：累计收取果实总数、当前最高奖牌、全部档位与下一档进度
    total_harvested: int = 0
    medal: str | None = None
    medals: list[PetMedal] = []
    next_medal: str | None = None
    next_medal_threshold: int | None = None
    # 宠物语音音色预设 id；为空表示用户未主动配置（前端套用默认档）
    voice_preset: str | None = None


class HarvestResult(BaseModel):
    fruits: int
    tree_growth: float
    harvested: int
    total_harvested: int = 0
    medal: str | None = None
    new_medal: str | None = None
    harvestable_cycles: int = 0


class FeedResult(BaseModel):
    level: int
    exp: int
    exp_max: int
    tree_growth: float
    tree_stage: str
    leveled_up: bool

class PetChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

class PetVoiceRequest(BaseModel):
    voice_preset: str = Field(..., min_length=1, max_length=50)


class PetVoiceResult(BaseModel):
    voice_preset: str
