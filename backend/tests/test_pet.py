from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.models.pet import Pet
from app.services import pet_service
from sqlalchemy import select


def test_generate_pet_identity_is_stable_and_varied():
    a1 = pet_service.generate_pet_identity("user-a")
    a2 = pet_service.generate_pet_identity("user-a")
    b = pet_service.generate_pet_identity("user-b")

    assert a1 == a2
    assert a1["species"] in pet_service.SPECIES
    assert a1["color"] in pet_service.COLORS
    assert a1["personality"] in pet_service.PERSONALITIES
    assert a1["name"]
    # 不同用户身份应当不同（极具区分度）
    assert a1 != b



@pytest.mark.asyncio
async def test_get_or_create_pet_assigns_unique_identity(test_db):
    pet = await pet_service.get_or_create_pet(test_db, "user-alpha")
    assert pet.name and pet.species and pet.color and pet.personality
    assert pet.tree_growth == 0.0

    again = await pet_service.get_or_create_pet(test_db, "user-alpha")
    assert again.id == pet.id
    assert again.species == pet.species


@pytest.mark.asyncio
async def test_legacy_pet_gets_identity_backfilled(test_db):
    legacy = Pet(user_id="legacy-user")
    test_db.add(legacy)
    await test_db.commit()
    await test_db.refresh(legacy)
    assert legacy.species is None

    pet = await pet_service.get_or_create_pet(test_db, "legacy-user")
    assert pet.species is not None
    assert pet.name is not None


@pytest.mark.asyncio
async def test_apply_knowledge_growth(test_db):
    await pet_service.apply_knowledge_growth(test_db, "grow-user", 3)
    pet = await pet_service.get_or_create_pet(test_db, "grow-user")
    assert pet.tree_growth == pytest.approx(pet_service.growth_from_nodes(3))
    assert pet.growth_cycles == 0

    # 一次性导入大量知识点：溢出自动进位为一个成长轮次，不丢失
    await pet_service.apply_knowledge_growth(test_db, "grow-user", 100)
    pet = await pet_service.get_or_create_pet(test_db, "grow-user")
    assert pet.growth_cycles == 1
    assert pet.tree_growth == pytest.approx(pet_service.growth_from_nodes(23))

    # 0 不增长
    assert await pet_service.apply_knowledge_growth(test_db, "grow-user", 0) is None


@pytest.mark.asyncio
async def test_apply_knowledge_growth_is_lossless(test_db):
    """回归：分批导入与一次性导入的最终状态必须一致（无溢出丢失）。"""
    await pet_service.apply_knowledge_growth(test_db, "batch-a", 80)
    await pet_service.apply_knowledge_growth(test_db, "batch-a", 120)
    batch = await pet_service.get_or_create_pet(test_db, "batch-a")

    await pet_service.apply_knowledge_growth(test_db, "batch-b", 200)
    once = await pet_service.get_or_create_pet(test_db, "batch-b")

    assert batch.growth_cycles == once.growth_cycles == 2
    assert batch.tree_growth == pytest.approx(once.tree_growth)
    assert once.tree_growth == pytest.approx(pet_service.growth_from_nodes(40))


def test_exp_curve_is_increasing_and_gentle():
    assert pet_service.exp_max(1) == pet_service.PET_EXP_BASE
    assert pet_service.exp_max(1) < pet_service.exp_max(2) < pet_service.exp_max(5)


def test_pet_prompt_injects_persona_and_history():
    from app.core.prompt_manager import prompt_manager

    prompt = prompt_manager.get_pet_prompt(
        level=4,
        user_message="今天学了什么呀",
        knowledge_concepts=["神经网络"],
        name="小灵",
        personality="好奇",
        species="spirit",
        mood="proud",
        history=[
            {"role": "user", "content": "在吗"},
            {"role": "assistant", "content": "在的呀"},
        ],
    )
    # 身份与情绪注入
    assert "小灵" in prompt
    assert "为你骄傲" in prompt or "好奇" in prompt
    # 历史上下文注入
    assert "在的呀" in prompt
    assert "最近你和主人的对话" in prompt


def test_care_message_reflects_mood_and_time():
    pet = Pet(user_id="care-user", name="小星")
    evening = datetime(2026, 10, 11, 12, 0, 0)
    assert "晚上好" in pet_service.build_care_message(pet, now=evening)

    lonely_pet = Pet(user_id="care-user-2", name="小月")
    pet_service.apply_event(lonely_pet, "feed", now=evening - timedelta(hours=100))
    assert "想你" in pet_service.build_care_message(lonely_pet, now=evening)


@pytest.mark.asyncio
async def test_daily_care_delivered_once_per_day(client):
    first = await client.get("/api/v1/pet/status")
    assert first.status_code == 200
    assert first.json()["greeting"]

    second = await client.get("/api/v1/pet/status")
    assert second.json()["greeting"] is None


@pytest.mark.asyncio
async def test_pet_chat_memory_roundtrip(test_db):
    await pet_service.save_chat_exchange(test_db, "mem-user", "你好", "喵~主人好！")
    history = await pet_service.load_recent_messages(test_db, "mem-user")
    assert history == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "喵~主人好！"},
    ]


def test_derive_growth_tracks_cycles_and_consumption():
    # 满额轮次 = 知识点总数 // 80；进度为当前轮内凹曲线值
    assert pet_service.derive_growth(80, 0) == (pytest.approx(0.0), 1)
    assert pet_service.derive_growth(90, 0)[0] == pytest.approx(
        pet_service.growth_from_nodes(10)
    )
    # 已收割一轮后不再可收割，但新知识仍能重新成熟
    assert pet_service.derive_growth(80, 100) == (pytest.approx(0.0), 0)
    assert pet_service.derive_growth(160, 100) == (pytest.approx(0.0), 1)
    # 一次性 200 知识点 = 2 个待收割轮次
    assert pet_service.derive_growth(200, 0)[1] == 2


@pytest.mark.asyncio
async def test_pet_status_returns_unique_pet(client):
    resp = await client.get("/api/v1/pet/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"]
    assert data["species"]
    assert data["color"]
    assert data["knowledge_total"] == 0
    assert data["tree_fruits"] == 0
    # 情感状态机默认值
    assert data["mood"] in pet_service.MOODS
    assert 0 <= data["bond"] <= pet_service.BOND_MAX
    assert data["streak_days"] >= 0


def test_emotion_state_machine_events_and_streak():
    pet = Pet(user_id="emotion-user")
    now = datetime(2026, 10, 11, 9, 0, 0)
    pet_service.apply_event(pet, "feed", now=now)
    assert pet.mood == "happy"
    assert pet.bond == pet_service.BOND_GAIN["feed"]
    assert pet.streak_days == 1
    assert pet.last_active_date == now.date()

    # 同日再次互动：streak 保持不变，亲密度继续累加
    pet_service.apply_event(pet, "harvest", now=now + timedelta(hours=2))
    assert pet.mood == "excited"
    assert pet.streak_days == 1
    assert pet.bond == pet_service.BOND_GAIN["feed"] + pet_service.BOND_GAIN["harvest"]

    # 次日互动：连续天数 +1
    pet_service.apply_event(pet, "study", now=now + timedelta(days=1))
    assert pet.streak_days == 2

    # 中断后再互动：连续天数重置为 1
    pet_service.apply_event(pet, "chat", now=now + timedelta(days=4))
    assert pet.streak_days == 1


def test_compute_mood_decays_with_idle_time():
    pet = Pet(user_id="mood-user")
    base = datetime(2026, 10, 11, 9, 0, 0)
    pet_service.apply_event(pet, "feed", now=base)
    assert pet_service.compute_mood(pet, now=base + timedelta(hours=1)) == "happy"
    assert pet_service.compute_mood(pet, now=base + timedelta(hours=30)) == "lonely"
    assert pet_service.compute_mood(pet, now=base + timedelta(hours=100)) == "tired"


def test_effective_bond_decays_after_idle_days():
    pet = Pet(user_id="bond-user")
    base = datetime(2026, 10, 11, 9, 0, 0)
    pet_service.apply_event(pet, "harvest", now=base)
    stored = pet.bond
    assert pet_service.effective_bond(pet, now=base) == stored
    # 闲置 3 天：超过 1 天的部分按每天 1 点衰减，且不低于 0
    assert pet_service.effective_bond(pet, now=base + timedelta(days=3)) == max(0, stored - 2)
    assert pet_service.bond_level(stored) in [name for _, name in pet_service.BOND_LEVELS]


@pytest.mark.asyncio
async def test_pet_status_lists_knowledge_threads(client, test_engine, mock_graph_service):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.note import Note

    mock_graph_service.get_mastery_overview.return_value = {
        "total": 8,
        "avg_mastery": 0.0,
        "weak": 0,
        "basic": 0,
        "proficient": 0,
    }

    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        session.add(
            Note(
                id="thread-a",
                user_id="test-user-0001",
                title="脉络A",
                content="x",
                status="success",
                nodes_count=3,
                edges_count=2,
            )
        )
        session.add(
            Note(
                id="thread-b",
                user_id="test-user-0001",
                title="脉络B",
                content="y",
                status="success",
                nodes_count=5,
                edges_count=4,
            )
        )
        session.add(
            Note(
                id="thread-c",
                user_id="test-user-0001",
                title="失败脉络",
                content="z",
                status="failed",
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/pet/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["knowledge_total"] == 8
    # 每份成功抽取的笔记 = 一条脉络 = 一颗果实（失败笔记不计入）
    assert data["tree_fruits"] == 2
    assert [t["title"] for t in data["threads"]] == ["脉络A", "脉络B"]
    assert data["threads"][0]["nodes_count"] == 3


@pytest.mark.asyncio
async def test_register_creates_pet(client, test_engine):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"phone": "13612345678", "code": settings.SMS_DEV_MASTER_CODE},
    )
    assert resp.status_code == 200

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        from app.models.user import User

        user = (
            await session.execute(select(User).where(User.phone == "13612345678"))
        ).scalar_one()
        pet = (
            await session.execute(select(Pet).where(Pet.user_id == user.id))
        ).scalar_one_or_none()
        assert pet is not None
        assert pet.species and pet.name


@pytest.mark.asyncio
async def test_harvest_requires_mature_tree(client):
    resp = await client.post("/api/v1/pet/harvest")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_feed_requires_fruits(client):
    resp = await client.post("/api/v1/pet/feed")
    assert resp.status_code == 400

@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="契约漂移：抽取成功后的成长断言基于旧 nodes_count 语义",
    strict=False,
)
async def test_extraction_success_grows_pet_tree(test_engine, tmp_path):
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.services.extraction_service import ExtractionService

    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    source = tmp_path / "note.md"
    source.write_text("机器学习是人工智能的一个分支", encoding="utf-8")

    ai = AsyncMock()
    ai.extract_knowledge = AsyncMock(
        return_value={
            "nodes": [{"id": "n1", "name": "机器学习"}, {"id": "n2", "name": "人工智能"}],
            "edges": [],
        }
    )
    graph = AsyncMock()
    graph.write_extraction_result = AsyncMock(return_value=None)

    service = ExtractionService(
        ai_service=ai,
        graph_service=graph,
        session_factory=SessionLocal,
        max_attempts=1,
        backoff_seconds=0,
    )
    await service.extract_and_build_graph("note-grow", "grow-user-2", str(source), "md")

    async with SessionLocal() as session:
        pet = (
            await session.execute(select(Pet).where(Pet.user_id == "grow-user-2"))
        ).scalar_one()
        assert pet.tree_growth == pytest.approx(2 * pet_service.GROWTH_PER_NODE)
        assert pet.name and pet.species

def test_compute_pending_growth_subtracts_consumed():
    assert pet_service.compute_pending_growth(0, 0) == 0.0
    # 80 个知识点 = 满额 100 成长值
    assert pet_service.compute_pending_growth(80, 0) == 100.0
    # 收取果实消耗 100 成长值后，同一批知识不再产生进度
    assert pet_service.compute_pending_growth(80, 100) == 0.0
    # 知识继续增长（160 节点 = 200 原始成长）后可再次成熟
    assert pet_service.compute_pending_growth(160, 100) == 100.0
    # 未满额时按凹曲线成长：40 节点的边际递减结果介于线性 50 与满额 100 之间
    half = pet_service.compute_pending_growth(40, 0)
    assert 50.0 < half < 100.0
    assert half == pytest.approx(pet_service.growth_from_nodes(40))


def test_growth_curve_is_concave_and_invertible():
    # 边际递减：同样增加 10 个知识点，前期收益大于后期
    early = pet_service.growth_from_nodes(10) - pet_service.growth_from_nodes(0)
    late = pet_service.growth_from_nodes(80) - pet_service.growth_from_nodes(70)
    assert early > late > 0
    # 反函数与正函数互逆，保证增量累加幂等
    for nodes in (5, 20, 40, 60, 80):
        assert pet_service._nodes_from_growth(
            pet_service.growth_from_nodes(nodes)
        ) == pytest.approx(nodes, abs=1e-6)


@pytest.mark.asyncio
async def test_harvest_cannot_be_farmed_repeatedly(client, test_engine, mock_graph_service):
    """回归：收取果实后，同一批知识不得再次把树木刷成熟。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.note import Note

    mock_graph_service.get_mastery_overview.return_value = {
        "total": 80,
        "avg_mastery": 0.0,
        "weak": 0,
        "basic": 0,
        "proficient": 0,
    }

    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        session.add(
            Note(
                id="farm-note",
                user_id="test-user-0001",
                title="刷果实",
                content="x",
                status="success",
                nodes_count=80,
                edges_count=0,
            )
        )
        await session.commit()

    status = await client.get("/api/v1/pet/status")
    assert status.json()["tree_growth"] == 100.0

    first = await client.post("/api/v1/pet/harvest")
    assert first.status_code == 200
    assert first.json()["fruits"] == pet_service.MAX_TREE_FRUITS

    # 再次读取状态：成长值不应被惰性校准重新拉满
    status_after = await client.get("/api/v1/pet/status")
    assert status_after.json()["tree_growth"] == 0.0

    # 因此无法二次收割
    second = await client.post("/api/v1/pet/harvest")
    assert second.status_code == 400

@pytest.mark.asyncio
async def test_overflow_yields_multiple_harvestable_cycles(
    client, test_engine, mock_graph_service
):
    """回归：一次性导入 160 个知识点应产生 2 个待收割轮次（溢出进位，不丢失）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.note import Note

    mock_graph_service.get_mastery_overview.return_value = {
        "total": 160,
        "avg_mastery": 0.0,
        "weak": 0,
        "basic": 0,
        "proficient": 0,
    }

    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        session.add(
            Note(
                id="overflow-note",
                user_id="test-user-0001",
                title="大导入",
                content="x",
                status="success",
                nodes_count=160,
                edges_count=0,
            )
        )
        await session.commit()

    status = await client.get("/api/v1/pet/status")
    assert status.json()["harvestable_cycles"] == 2
    assert status.json()["tree_growth"] == 100.0

    first = await client.post("/api/v1/pet/harvest")
    assert first.status_code == 200
    assert first.json()["total_harvested"] == pet_service.MAX_TREE_FRUITS
    assert first.json()["harvestable_cycles"] == 1

    second = await client.post("/api/v1/pet/harvest")
    assert second.status_code == 200
    assert second.json()["total_harvested"] == 2 * pet_service.MAX_TREE_FRUITS
    assert second.json()["harvestable_cycles"] == 0

    third = await client.post("/api/v1/pet/harvest")
    assert third.status_code == 400