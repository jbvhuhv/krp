from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# 全站统一时间戳序列化：数据库中的 naive datetime 视为 UTC，输出带时区的 ISO 串（以 Z 结尾）。
UtcDateTime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str)]
