"""上传大小限制工具：先看声明大小，再分块读取并累计计数。

为什么需要：
    原实现是 ``content = await file.read()`` 之后再比较 ``len(content)``，
    超限文件同样会被完整读进内存。2C2G 的机器上一个数 GB 的请求即可把进程打爆（OOM）。

行为差异：
    超限时返回 413（Payload Too Large），而不是原来的 400。
    若前端对 400 做了特殊提示，需要同步调整。
"""

from fastapi import HTTPException, UploadFile, status

CHUNK_SIZE = 64 * 1024


def _too_large(limit_bytes: int) -> HTTPException:
    limit_mb = max(1, limit_bytes // (1024 * 1024))
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=f"文件超过 {limit_mb}MB 上限，请压缩后重试",
    )


async def read_upload_limited(
    upload: UploadFile, max_bytes: int, *, chunk_size: int = CHUNK_SIZE
) -> bytes:
    """分块读取上传内容；一旦累计超过 max_bytes 立即中断并抛 413。

    - 先利用 UploadFile.size（若框架提供）做快速拒绝，避免无谓读取
    - 再流式累计，防止伪造 Content-Length 绕过
    """
    declared = getattr(upload, "size", None)
    if declared is not None and declared > max_bytes:
        raise _too_large(max_bytes)

    buffer = bytearray()
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise _too_large(max_bytes)
    return bytes(buffer)
