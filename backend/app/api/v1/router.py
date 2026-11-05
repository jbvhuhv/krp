from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    avatar,
    brainstorm,
    community,
    demo,
    graph,
    notes,
    notifications,
    pet,
    reflection,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(notes.router, prefix="/notes", tags=["笔记"])
api_router.include_router(graph.router, prefix="/graph", tags=["知识图谱"])
api_router.include_router(brainstorm.router, prefix="/brainstorm", tags=["AI 辅助手绘"])
api_router.include_router(reflection.router, prefix="/reflection", tags=["反思"])
api_router.include_router(avatar.router, prefix="/avatar", tags=["数字分身"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["通知"])
api_router.include_router(community.router, prefix="/community", tags=["知识广场"])
api_router.include_router(demo.router, prefix="/demo", tags=["示例数据"])
api_router.include_router(pet.router, prefix="/pet", tags=["宠物"])
