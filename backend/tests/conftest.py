import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock

import app.models.avatar  # noqa: F401
import app.models.community  # noqa: F401
import app.models.note  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.pet  # noqa: F401
import app.models.reflection  # noqa: F401
from app.api.deps import (
    get_avatar_service,
    get_current_user_id,
    get_db,
    get_extraction_service,
    get_graph_service,
    get_notification_service,
    get_ocr_service,
    get_optional_user_id,
    get_reflection_service,
)
from app.core.config import settings
from app.main import app
from app.models.user import Base

TEST_USER_ID = "test-user-0001"


@pytest.fixture
def temp_upload_dir(tmp_path_factory):
    upload_dir = tmp_path_factory.mktemp("uploads")
    original = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(upload_dir)
    yield upload_dir
    settings.UPLOAD_DIR = original


@pytest.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_db(test_engine):
    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest.fixture
def mock_extraction_service():
    service = AsyncMock()
    service.extract_and_build_graph = AsyncMock(return_value={"nodes": [], "edges": []})
    return service


@pytest.fixture
def mock_ocr_service():
    service = AsyncMock()
    service.recognize_bytes = AsyncMock(return_value="识别出的图片文字")
    service.recognize = AsyncMock(return_value="识别出的图片文字")
    return service


@pytest.fixture
def mock_graph_service():
    service = AsyncMock()
    service.create_node = AsyncMock(return_value="mock-node-id")
    service.create_edge = AsyncMock(return_value="mock-edge-id")
    service.get_user_graph = AsyncMock(return_value={"nodes": [], "edges": []})
    service.get_mastery_overview = AsyncMock(
        return_value={"total": 0, "avg_mastery": 0.0, "weak": 0, "basic": 0, "proficient": 0}
    )
    service.get_node_detail = AsyncMock(return_value=None)
    service.update_node = AsyncMock(return_value=None)
    service.is_descendant = AsyncMock(return_value=False)
    service.count_nodes_by_origin = AsyncMock(return_value=0)
    service.delete_node = AsyncMock(return_value=True)
    service.delete_subtree = AsyncMock(return_value=1)
    service.update_mastery = AsyncMock(return_value={"id": "node-1", "mastery": 80.0})
    service.get_nodes_for_review = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_reflection_service():
    service = AsyncMock()
    service.get_today_questions = AsyncMock(return_value=[])
    service.generate_questions = AsyncMock(return_value=[])
    service.evaluate_answer = AsyncMock(return_value=None)
    service.get_history = AsyncMock(return_value={"items": [], "total": 0})
    service.get_mastery_trend = AsyncMock(return_value={"nodes": [], "timeline": []})
    service.get_schedule = AsyncMock(return_value=None)
    service.update_schedule = AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_avatar_service():
    service = MagicMock()
    service.publish = AsyncMock(return_value=None)
    service.unpublish = AsyncMock(return_value=None)
    service.update_config = AsyncMock(return_value=None)
    service.get_avatar_for_user = AsyncMock(return_value=None)
    service.get_by_avatar_id = AsyncMock(return_value=None)
    service.get_stats = AsyncMock(return_value=None)
    service.rag_search = AsyncMock(return_value=[])
    service.build_share_url = MagicMock(return_value="http://test/avatar/share-token")
    service.resolve_knowledge_scope = AsyncMock(
        side_effect=lambda avatar: list(getattr(avatar, "knowledge_scope", None) or [])
    )
    return service


@pytest.fixture
def mock_notification_service():
    service = MagicMock()
    service.create = AsyncMock(return_value=None)
    service.list_for_user = AsyncMock(
        return_value={"items": [], "total": 0, "unread": 0}
    )
    service.mark_read = AsyncMock(return_value=None)
    return service


@pytest.fixture
async def client(
    test_engine,
    temp_upload_dir,
    mock_extraction_service,
    mock_graph_service,
    mock_reflection_service,
    mock_avatar_service,
    mock_notification_service,
    mock_ocr_service,
):
    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID
    app.dependency_overrides[get_optional_user_id] = lambda: TEST_USER_ID
    app.dependency_overrides[get_extraction_service] = lambda: mock_extraction_service
    app.dependency_overrides[get_graph_service] = lambda: mock_graph_service
    app.dependency_overrides[get_ocr_service] = lambda: mock_ocr_service
    app.dependency_overrides[get_reflection_service] = lambda: mock_reflection_service
    app.dependency_overrides[get_avatar_service] = lambda: mock_avatar_service
    app.dependency_overrides[get_notification_service] = lambda: mock_notification_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()