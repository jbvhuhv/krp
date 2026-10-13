from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.ai_deps import get_ai_service
from app.api.deps.graph_deps import get_graph_service
from app.core.database import get_db


def build_avatar_service(db: AsyncSession):
    from app.services.avatar_service import AvatarService

    return AvatarService(
        db=db,
        ai_service=get_ai_service(),
        graph_service=get_graph_service(),
    )


async def get_avatar_service(
    db: AsyncSession = Depends(get_db),
    ai_service=Depends(get_ai_service),
    graph_service=Depends(get_graph_service),
):
    from app.services.avatar_service import AvatarService

    return AvatarService(
        db=db,
        ai_service=ai_service,
        graph_service=graph_service,
    )
