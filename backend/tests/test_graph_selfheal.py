"""自愈链路的回归测试：Neo4j 晚就绪时，索引与演示数据必须补做。

背景（2026-11-05 实测暴露）
--------------------------
`init_vector_index` / `init_property_indexes` / `bootstrap_neo4j` /
`normalize_last_reviewed` 原本只在 lifespan 里各跑一次。Neo4j 比应用晚就绪时
它们会全部失败，而自愈协程只把 `neo4j_available` 翻回 True、不重跑初始化，
结果是：`/health` 显示已连上 Neo4j，但属性索引永久缺失（图谱查询退化为全标签
扫描），演示图谱也永远不导入。

本文件锁住两件事：
1. 自愈成功后必须调用 `_warm_graph`；
2. `/health?deep=1` 探测失败时要把可用标志翻回 False，否则自愈协程
   （只在标志为 False 时才重探）永远不会再尝试，而浅检查会继续报 "neo4j"。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.main as main_module
from app.services import graph as graph_module


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def run(self, *args, **kwargs):
        return _FakeResult({"ok": 1})


class _FakeDriver:
    """只实现 recover 协程用到的那一小部分接口。"""

    def session(self):
        return _FakeSession()


async def test_recovery_runs_warm_up_after_neo4j_comes_back(monkeypatch):
    state = {"available": False}
    warmed = []

    monkeypatch.setattr(graph_module, "neo4j_available", lambda: state["available"])

    def _set(value):
        state["available"] = value

    monkeypatch.setattr(graph_module, "set_neo4j_available", _set)

    async def _fake_warm(driver):
        warmed.append(driver)

    monkeypatch.setattr(main_module, "_warm_graph", _fake_warm)

    task = asyncio.create_task(
        main_module._recover_graph_backend(_FakeDriver(), interval=0.01)
    )
    try:
        for _ in range(200):
            if warmed:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert state["available"] is True, "自愈后应把可用标志切回 True"
    assert len(warmed) == 1, "自愈后必须补跑一次 _warm_graph（索引/演示数据）"


async def test_warm_up_is_idempotent_sequence(monkeypatch):
    """_warm_graph 应依次完成索引、演示数据、数据规范化；重复调用不出错。"""
    calls = []

    def _record(name):
        async def _inner(*args, **kwargs):
            calls.append(name)

        return _inner

    import app.core.demo_bootstrap as demo_bootstrap
    import app.core.graph_migrations as graph_migrations

    monkeypatch.setattr(graph_module, "init_vector_index", _record("vector"))
    monkeypatch.setattr(graph_module, "init_property_indexes", _record("property"))
    monkeypatch.setattr(demo_bootstrap, "bootstrap_neo4j", _record("demo"))
    monkeypatch.setattr(graph_migrations, "normalize_last_reviewed", _record("migrate"))

    await main_module._warm_graph(MagicMock())
    await main_module._warm_graph(MagicMock())

    assert calls == ["vector", "property", "demo", "migrate"] * 2


async def test_deep_health_flips_flag_when_probe_fails(client, monkeypatch):
    """deep 检查失败时要把标志翻回 False，且响应里的 graph_backend 不能自相矛盾。"""
    from app.core import database as database_module

    class _BrokenDriver:
        def session(self):
            raise RuntimeError("bolt 连接已失效")

    state = {"available": True}
    monkeypatch.setattr(graph_module, "neo4j_available", lambda: state["available"])
    monkeypatch.setattr(
        graph_module, "set_neo4j_available", lambda v: state.__setitem__("available", v)
    )
    monkeypatch.setattr(database_module, "neo4j_driver", _BrokenDriver())

    resp = await client.get("/health?deep=1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["neo4j"].startswith("error:")
    assert body["graph_backend"] == "local", "标志已翻回 False，响应必须与之一致"
    assert state["available"] is False
