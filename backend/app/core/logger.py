"""统一日志工具：固定日志格式并向每条记录注入 trace_id。"""

import logging
import sys
from contextvars import ContextVar

LOG_FORMAT = "[%(asctime)s] [%(trace_id)s] [%(name)s] [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_TRACE_ID = "-"

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default=DEFAULT_TRACE_ID)
_configured = False


def set_trace_id(trace_id: str):
    """绑定当前上下文的 trace_id，返回用于恢复的 token。"""
    return _trace_id_var.set(trace_id or DEFAULT_TRACE_ID)


def get_trace_id() -> str:
    """读取当前上下文的 trace_id。"""
    return _trace_id_var.get()


def reset_trace_id(token) -> None:
    """请求结束后恢复上下文，避免 trace_id 跨请求泄漏。"""
    try:
        _trace_id_var.reset(token)
    except (ValueError, LookupError):
        _trace_id_var.set(DEFAULT_TRACE_ID)


class _TraceIdFilter(logging.Filter):
    """把 trace_id 注入每条日志记录，显式传入优先，其次取上下文。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "trace_id", None):
            record.trace_id = _trace_id_var.get()
        return True


class TraceLogger(logging.Logger):
    """支持以 trace_id 关键字显式覆盖上下文 trace_id 的 Logger。"""

    def _log(self, level, msg, args, exc_info=None, extra=None,
             stack_info=False, stacklevel=1, trace_id=None):
        if trace_id:
            extra = dict(extra) if extra else {}
            extra["trace_id"] = trace_id
        super()._log(level, msg, args, exc_info, extra, stack_info, stacklevel)


logging.setLoggerClass(TraceLogger)


def setup_logging(level: int | None = None) -> None:
    """配置根 logger 的处理器与格式，重复调用只生效一次。"""
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    handler.addFilter(_TraceIdFilter())
    root.addHandler(handler)
    root.setLevel(level if level is not None else logging.INFO)
    _configured = True


def get_logger(name: str | None = None) -> TraceLogger:
    """获取统一配置的 logger，业务代码统一由此获取。"""
    setup_logging()
    return logging.getLogger(name)
