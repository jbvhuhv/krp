"""集中定义全局常量。

避免魔法数字 / 魔法字符串散落在各模块中，便于统一维护。
"""

# —— 笔记知识抽取状态（这 5 个值是 notes.status 字段的真实持久化取值）——
NOTE_STATUS = {
    "PENDING": "pending",
    "PROCESSING": "processing",
    "SUCCESS": "success",
    "EMPTY": "empty",
    "FAILED": "failed",
}

# —— 掌握度阈值（百分比）——
MASTERY_THRESHOLDS = {
    "WEAK": 60,
    "STRONG": 80,
}

# —— 宠物成长参数（成长数学模型的唯一权威来源）——
# 每 N 个知识点在树上结出一颗果实
PET_KNOWLEDGE_PER_FRUIT = 10
# 树上最多同时展示的果实数（满额即可收取）
PET_MAX_TREE_FRUITS = 8
# 达到满额成长所需知识点总数（8 颗果实 × 每颗 10 个知识点 = 80）
PET_KNOWLEDGE_FOR_FULL = PET_KNOWLEDGE_PER_FRUIT * PET_MAX_TREE_FRUITS
# 边际递减指数 >1：前期成长快、接近满额时越来越慢（成长曲线为凹函数）。
# 曲线 g(n)=100*(1-(1-n/80)^1.35)，保证 80 个知识点恰好满额。
PET_GROWTH_CONCAVITY = 1.35
# 初始边际成长率（每个知识点的成长值，随进度递减）；保留作为展示口径
PET_GROWTH_PER_NODE = 100.0 * PET_GROWTH_CONCAVITY / PET_KNOWLEDGE_FOR_FULL

# —— 宠物等级经验曲线 ——
# 升到下一级所需经验：base + step*(level-1)，线性递增。
# 前期升级快（快速正反馈），后期稳步提升，避免二次增长带来的长尾卡级。
PET_EXP_BASE = 60
PET_EXP_STEP = 30

# 兼容旧引用：以字典形式聚合成长参数
PET_GROWTH = {
    "KNOWLEDGE_PER_FRUIT": PET_KNOWLEDGE_PER_FRUIT,
    "MAX_TREE_FRUITS": PET_MAX_TREE_FRUITS,
    "KNOWLEDGE_FOR_FULL": PET_KNOWLEDGE_FOR_FULL,
    "GROWTH_CONCAVITY": PET_GROWTH_CONCAVITY,
    "GROWTH_PER_NODE": PET_GROWTH_PER_NODE,
}
