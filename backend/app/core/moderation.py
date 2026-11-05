"""UGC 内容初筛。

广场是作品被评委看到的第一屏，之前发帖/评论没有任何门槛：任意文本、任意长度、
无频率限制。这里做最低限度的第一道闸门——关键词初筛，把明显违法的内容挡在入库前。

边界要说清楚：关键词只能过滤「显而易见」的一类，不等同于内容审核。
真正的治理仍需要举报入口 + 人工复核，本模块只负责不把最脏的东西直接放上广场。
"""

from __future__ import annotations

import re
import unicodedata

from app.core.config import settings

# 内置基线：只收「入站即违规」的高危类目，避免误伤正常学术讨论。
# 每个词都是明确的违法/黑产服务，不含学科术语。
_BUILTIN_BLOCKED: tuple[str, ...] = (
    # 色情交易
    "约炮", "援交", "裸聊", "卖淫", "嫖娼",
    # 赌博与毒品
    "赌球", "博彩", "网赌", "开赌场", "冰毒", "摇头丸", "大麻代购",
    # 黑产服务（校园场景高发）
    "代考", "替考", "代写论文", "包过", "办假证", "假学历", "刻章办证",
    "代开发票", "出售发票", "洗钱", "跑分平台",
    # 武器与危险品
    "卖枪", "枪支买卖", "自制炸药", "管制刀具出售",
)

# 零宽字符与常见分隔符：用来绕过关键词匹配的惯用手法
_INVISIBLE = re.compile(r"[\u200b-\u200f\u2060\ufeff\u00ad]")
_SEPARATORS = re.compile(r"[\s\-_*·.。、,，|/\\]+")


def _normalize(text: str) -> str:
    """全角转半角、去零宽、去分隔符，让「代 考」「代\u200b考」也能命中。"""
    return _SEPARATORS.sub("", _INVISIBLE.sub("", unicodedata.normalize("NFKC", text))).lower()


def _blocked_words() -> tuple[str, ...]:
    extra = [
        w.strip().lower()
        for w in (settings.UGC_BLOCKED_WORDS or "").split(",")
        if w.strip()
    ]
    return _BUILTIN_BLOCKED + tuple(extra)


def find_violation(*fields: str | None) -> str | None:
    """返回命中的词（供日志脱敏记录），未命中返回 None。"""
    text = _normalize(" ".join(f for f in fields if f))
    if not text:
        return None
    for word in _blocked_words():
        if _normalize(word) in text:
            return word
    return None
