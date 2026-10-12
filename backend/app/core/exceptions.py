"""全局业务异常定义。"""

from typing import Any


class KnowledgeBaseException(Exception):
    """所有业务异常的基类，携带统一错误码与 HTTP 状态码。"""

    def __init__(self, message: str = "服务器内部错误", code: int = 500,
                 detail: Any = None, status_code: int = 500):
        self.message = message
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


class BadRequestException(KnowledgeBaseException):
    def __init__(self, message: str = "请求参数错误", detail: Any = None):
        super().__init__(message, code=400, detail=detail, status_code=400)


class UnauthorizedException(KnowledgeBaseException):
    def __init__(self, message: str = "未认证或登录已过期", detail: Any = None):
        super().__init__(message, code=401, detail=detail, status_code=401)


class ForbiddenException(KnowledgeBaseException):
    def __init__(self, message: str = "没有权限执行该操作", detail: Any = None):
        super().__init__(message, code=403, detail=detail, status_code=403)


class NotFoundException(KnowledgeBaseException):
    def __init__(self, message: str = "资源不存在", detail: Any = None):
        super().__init__(message, code=404, detail=detail, status_code=404)


class ServiceUnavailableException(KnowledgeBaseException):
    def __init__(self, message: str = "依赖服务不可用", detail: Any = None):
        super().__init__(message, code=503, detail=detail, status_code=503)
