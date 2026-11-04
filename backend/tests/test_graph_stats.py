
import pytest

pytestmark = pytest.mark.asyncio


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)

    async def single(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows, captured):
        self._rows = rows
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def run(self, query, **kwargs):
        self._captured["query"] = query
        self._captured["kwargs"] = kwargs
        return _FakeResult(self._rows)


class _FakeDriver:
    def __init__(self, rows, captured):
        self._rows = rows
        self._captured = captured

    def session(self):
        return _FakeSession(self._rows, self._captured)


def _service(rows, captured):
    from app.services.graph_service import GraphService

    return GraphService(driver=_FakeDriver(rows, captured))


async def test_mastery_overview_aggregates_on_server_side():
    captured: dict = {}
    svc = _service(
        [{"total": 2, "avg_mastery": 60.0, "weak": 1, "basic": 0, "proficient": 1}],
        captured,
    )

    overview = await svc.get_mastery_overview("u1")

    assert overview == {
        "total": 2,
        "avg_mastery": 60.0,
        "weak": 1,
        "basic": 0,
        "proficient": 1,
    }
    assert "node_type: $node_type" in captured["query"]
    assert captured["kwargs"]["node_type"] == "knowledge"


async def test_mastery_overview_empty_returns_zeros():
    captured: dict = {}
    svc = _service(
        [{"total": 0, "avg_mastery": None, "weak": 0, "basic": 0, "proficient": 0}],
        captured,
    )

    overview = await svc.get_mastery_overview("u1")

    assert overview == {
        "total": 0,
        "avg_mastery": 0.0,
        "weak": 0,
        "basic": 0,
        "proficient": 0,
    }


async def test_subject_stats_returns_server_aggregates():
    captured: dict = {}
    svc = _service(
        [{"subject": "ML", "node_count": 2, "avg_mastery": 60.0}],
        captured,
    )

    stats = await svc.get_subject_stats("u1")

    assert stats == [{"subject": "ML", "node_count": 2, "avg_mastery": 60.0}]
    assert "node_type: $node_type" in captured["query"]
    assert captured["kwargs"]["node_type"] == "knowledge"
    assert "未分类" in captured["kwargs"]["noise_subjects"]


async def test_subject_distribution_maps_grouped_rows():
    captured: dict = {}
    svc = _service(
        [{"subject": "ML", "cnt": 3}, {"subject": "未分类", "cnt": 1}],
        captured,
    )

    distribution = await svc.get_subject_distribution("u1")

    assert distribution == {"ML": 3, "未分类": 1}
    assert captured["kwargs"]["unclassified"] == "未分类"


async def test_get_nodes_for_review_filters_knowledge_only():
    from app.services.graph_service import GraphService

    captured: dict = {}
    svc = GraphService(driver=_FakeDriver([], captured))

    nodes = await svc.get_nodes_for_review("u1")

    assert nodes == []
    assert "node_type: $node_type" in captured["query"]
    assert captured["kwargs"]["node_type"] == "knowledge"
