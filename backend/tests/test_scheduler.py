from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


class _FakeResult:
    def __init__(self, users):
        self._users = users

    def scalars(self):
        return self

    def all(self):
        return self._users


class _FakeDB:
    def __init__(self, users):
        self._users = users

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._users)


class _FakeSessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _patch_scheduler_deps(monkeypatch, sched, users, generate_side_effect):
    db = _FakeDB(users)
    monkeypatch.setattr(sched, "AsyncSessionLocal", lambda: _FakeSessionCtx(db))
    monkeypatch.setattr(sched, "get_ai_service", lambda: object())
    monkeypatch.setattr(sched, "get_graph_service", lambda: object())

    reflection_service = MagicMock()
    reflection_service.generate_questions = AsyncMock(side_effect=generate_side_effect)
    monkeypatch.setattr(
        sched, "build_reflection_service", lambda d, ai, g: reflection_service
    )

    notification_service = MagicMock()
    notification_service.create = AsyncMock()
    monkeypatch.setattr(
        sched, "build_notification_service", lambda d: notification_service
    )
    return reflection_service, notification_service


class TestDailyReflectionJob:
    async def test_notifies_users_with_questions(self, monkeypatch):
        import app.scheduler as sched

        users = [SimpleNamespace(id="u1"), SimpleNamespace(id="u2")]
        _, notification_service = _patch_scheduler_deps(
            monkeypatch, sched, users, [[object(), object()], [object()]]
        )

        result = await sched.run_daily_reflection_job()

        assert result == {"users_processed": 2, "notified": 2}
        assert notification_service.create.await_count == 2
        first_call = notification_service.create.call_args_list[0].kwargs
        assert first_call["type"] == "reflection"
        assert first_call["title"] == "今日反思提醒"

    async def test_skips_users_without_questions(self, monkeypatch):
        import app.scheduler as sched

        users = [SimpleNamespace(id="u1")]
        _, notification_service = _patch_scheduler_deps(
            monkeypatch, sched, users, [[]]
        )

        result = await sched.run_daily_reflection_job()

        assert result == {"users_processed": 0, "notified": 0}
        notification_service.create.assert_not_called()

    async def test_continues_when_one_user_fails(self, monkeypatch):
        import app.scheduler as sched

        users = [SimpleNamespace(id="u1"), SimpleNamespace(id="u2")]
        _, notification_service = _patch_scheduler_deps(
            monkeypatch,
            sched,
            users,
            [RuntimeError("生成失败"), [object()]],
        )

        result = await sched.run_daily_reflection_job()

        assert result == {"users_processed": 1, "notified": 1}
        assert notification_service.create.await_count == 1

    async def test_no_users(self, monkeypatch):
        import app.scheduler as sched

        _, notification_service = _patch_scheduler_deps(monkeypatch, sched, [], [])

        result = await sched.run_daily_reflection_job()

        assert result == {"users_processed": 0, "notified": 0}


class TestSchedulerSetup:
    async def test_setup_registers_daily_job(self, monkeypatch):
        import app.scheduler as sched

        monkeypatch.setattr(sched.settings, "REFLECTION_CRON_HOUR", 8)
        monkeypatch.setattr(sched.settings, "REFLECTION_CRON_MINUTE", 30)

        sched.scheduler.remove_all_jobs()
        try:
            sched.setup_scheduler()
            job = sched.scheduler.get_job(sched.JOB_ID)
            assert job is not None
        finally:
            sched.shutdown_scheduler()

    async def test_shutdown_when_not_running(self):
        import app.scheduler as sched

        sched.shutdown_scheduler()
        assert sched.scheduler.running is False
