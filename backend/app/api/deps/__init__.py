from app.api.deps.ai_deps import get_ai_service
from app.api.deps.auth_deps import (
    get_current_user,
    get_current_user_db,
    get_current_user_id,
    get_optional_user_id,
    oauth2_scheme,
)
from app.api.deps.avatar_deps import build_avatar_service, get_avatar_service
from app.api.deps.graph_deps import get_graph_service
from app.api.deps.notes_deps import get_extraction_service, get_ocr_service
from app.api.deps.notification_deps import (
    build_notification_service,
    get_notification_service,
)
from app.api.deps.reflection_deps import (
    build_reflection_service,
    get_reflection_service,
)
from app.core.database import get_db

__all__ = [
    "build_avatar_service",
    "build_notification_service",
    "build_reflection_service",
    "get_ai_service",
    "get_avatar_service",
    "get_current_user",
    "get_current_user_db",
    "get_current_user_id",
    "get_db",
    "get_extraction_service",
    "get_graph_service",
    "get_notification_service",
    "get_ocr_service",
    "get_optional_user_id",
    "get_reflection_service",
    "oauth2_scheme",
]
