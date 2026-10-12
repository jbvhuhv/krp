import json
import os
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from app.api.deps import (
    build_avatar_service,
    get_avatar_service,
    get_current_user_id,
)
from app.core.config import DEFAULT_WELCOME_MESSAGE, settings
from app.core.database import AsyncSessionLocal
from app.schemas.avatar import (
    AvatarConfig,
    AvatarOut,
    AvatarPublishOut,
    AvatarStats,
    ConversationDetail,
    ConversationList,
    KnowledgeProfile,
)
from app.services.avatar_service import AvatarService

router = APIRouter()

_AVATAR_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_AVATAR_MAX_SIZE = 5 * 1024 * 1024
_MAGIC_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def _detect_image_ext(header: bytes) -> str | None:
    for sig, ext in _MAGIC_SIGNATURES:
        if header.startswith(sig):
            return ext
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    return None


def _to_avatar_out(avatar, scope: list[str] | None = None) -> AvatarOut:
    profile = None
    if avatar.profile:
        profile = KnowledgeProfile(**avatar.profile)
    knowledge_scope = scope if scope is not None else (avatar.knowledge_scope or [])
    return AvatarOut(
        avatar_id=avatar.id,
        status=avatar.status,
        tone=avatar.tone,
        welcome_message=avatar.welcome_message,
        knowledge_scope=knowledge_scope,
        avatar_url=getattr(avatar, "avatar_url", None),
        profile=profile,
    )


def _to_public_avatar_out(avatar, scope: list[str] | None = None) -> AvatarOut:
    """公开访问（访客视角）时仅回吐可展示的知识画像字段，
    不下发 mastery_overview / reflection_style 等主人学习状态细节。"""
    profile = None
    if avatar.profile:
        profile = KnowledgeProfile(
            domain_distribution=avatar.profile.get("domain_distribution", {}),
            summary=avatar.profile.get("summary", ""),
        )
    knowledge_scope = scope if scope is not None else (avatar.knowledge_scope or [])
    return AvatarOut(
        avatar_id=avatar.id,
        status=avatar.status,
        tone=avatar.tone,
        welcome_message=avatar.welcome_message,
        knowledge_scope=knowledge_scope,
        avatar_url=getattr(avatar, "avatar_url", None),
        profile=profile,
    )


@router.post("/avatar-image", status_code=status.HTTP_201_CREATED)
async def upload_avatar_image(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")
    if len(content) > _AVATAR_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="头像图片不能超过 5MB"
        )

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _AVATAR_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 PNG / JPG / JPEG / WEBP / GIF 格式",
        )
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="文件类型不是图片"
        )

    real_ext = _detect_image_ext(content[:16])
    if real_ext is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="文件内容不是有效图片"
        )

    avatar_dir = os.path.join(settings.UPLOAD_DIR, "avatars")
    os.makedirs(avatar_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{real_ext}"
    with open(os.path.join(avatar_dir, fname), "wb") as f:
        f.write(content)

    url = f"/uploads/avatars/{fname}"
    avatar = await avatar_service.update_config(user_id, {"avatar_url": url})
    scope = await avatar_service.resolve_knowledge_scope(avatar)
    return {"url": url, "avatar": _to_avatar_out(avatar, scope)}


@router.post("/publish", response_model=AvatarPublishOut, status_code=status.HTTP_201_CREATED)
async def publish_avatar(
    payload: AvatarConfig | None = None,
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    config = payload.model_dump() if payload else None
    avatar = await avatar_service.publish(user_id, config=config)
    return AvatarPublishOut(
        avatar_id=avatar.id,
        share_token=avatar.share_token,
        share_url=avatar_service.build_share_url(avatar),
        status=avatar.status,
    )


@router.put("/config", response_model=AvatarOut)
async def update_config(
    payload: AvatarConfig,
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    avatar = await avatar_service.update_config(user_id, payload.model_dump())
    scope = await avatar_service.resolve_knowledge_scope(avatar)
    return _to_avatar_out(avatar, scope)


@router.post("/unpublish", response_model=AvatarOut)
async def unpublish_avatar(
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    avatar = await avatar_service.unpublish(user_id)
    scope = await avatar_service.resolve_knowledge_scope(avatar)
    return _to_avatar_out(avatar, scope)


@router.get("/me", response_model=AvatarOut)
async def get_my_avatar(
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    avatar = await avatar_service.get_avatar_for_user(user_id)
    if avatar is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="尚未创建分身"
        )
    scope = await avatar_service.resolve_knowledge_scope(avatar)
    return _to_avatar_out(avatar, scope)


@router.get("/{avatar_id}/stats", response_model=AvatarStats)
async def get_stats(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    stats = await avatar_service.get_stats(user_id, avatar_id)
    if stats is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="分身不存在"
        )
    return AvatarStats(**stats)


@router.get("/{avatar_id}/conversations", response_model=ConversationList)
async def get_conversations(
    avatar_id: str,
    limit: int = Query(200, ge=1, le=500),
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    conversations = await avatar_service.get_conversations(
        user_id, avatar_id, limit=limit
    )
    if conversations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="分身不存在"
        )
    return ConversationList(conversations=conversations)


@router.get("/{avatar_id}/conversations/{visitor_id}", response_model=ConversationDetail)
async def get_conversation(
    avatar_id: str,
    visitor_id: str,
    user_id: str = Depends(get_current_user_id),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    detail = await avatar_service.get_conversation(user_id, avatar_id, visitor_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="分身不存在"
        )
    if not detail["messages"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
        )
    return ConversationDetail(**detail)


@router.get("/{avatar_id}", response_model=AvatarOut)
async def get_avatar(
    avatar_id: str,
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    avatar = await avatar_service.get_by_avatar_id(avatar_id)
    if avatar is None or avatar.status != "online":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="分身不存在或已下线"
        )
    scope = await avatar_service.resolve_knowledge_scope(avatar)
    return _to_public_avatar_out(avatar, scope)


def _parse_incoming(raw: str) -> tuple[str, str | None]:
    text = (raw or "").strip()
    if not text:
        return "", None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    if isinstance(data, dict):
        content = (data.get("content") or data.get("message") or "").strip()
        return content, data.get("visitor_id")
    return text, None


@router.websocket("/chat/{avatar_id}")
async def chat(websocket: WebSocket, avatar_id: str):
    await websocket.accept()
    async with AsyncSessionLocal() as db:
        avatar_service = build_avatar_service(db)
        avatar = await avatar_service.get_by_avatar_id(avatar_id)
        if avatar is None or avatar.status != "online":
            await websocket.send_json(
                {"type": "error", "message": "分身不存在或已下线"}
            )
            await websocket.close()
            return

        welcome = avatar.welcome_message or DEFAULT_WELCOME_MESSAGE
        await websocket.send_json({"type": "welcome", "message": welcome})

        history: list[dict] = []
        try:
            while True:
                raw = await websocket.receive_text()
                query, visitor_id = _parse_incoming(raw)
                if not query:
                    continue

                answer = ""
                async for event in avatar_service.stream_answer(
                    avatar, query, history=history, visitor_id=visitor_id
                ):
                    await websocket.send_json(event)
                    if event.get("type") == "chunk":
                        answer += event.get("content") or ""
                    elif event.get("type") == "done":
                        answer = event.get("answer") or answer
                    elif event.get("type") == "blocked":
                        answer = event.get("message") or ""

                history.append({"role": "user", "content": query})
                history.append({"role": "assistant", "content": answer})
                history = history[-10:]
        except WebSocketDisconnect:
            pass
