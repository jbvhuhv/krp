from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_current_user_id, get_db, get_graph_service
from app.core.constants import NOTE_STATUS
from app.core.logger import get_logger
from app.models.note import Note
from app.models.pet import Pet
from app.schemas.pet import (
    FeedResult,
    HarvestResult,
    KnowledgeThread,
    PetChatRequest,
    PetMedal,
    PetStatus,
    PetVoiceRequest,
    PetVoiceResult,
)
from app.services import pet_service
from app.services.ai_service import AIService
from app.services.graph_service import GraphService
from app.services.providers.base import AI_BUSY_MESSAGE, LLM_ERROR_TYPES

router = APIRouter()

logger = get_logger(__name__)


def _tree_stage(growth: float) -> str:
    if growth < 30:
        return "seedling"
    if growth < 70:
        return "sapling"
    return "tree"



async def _get_or_create_pet(db: AsyncSession, user_id: str) -> Pet:
    return await pet_service.get_or_create_pet(db, user_id)


async def _get_knowledge_threads(db: AsyncSession, user_id: str) -> list[KnowledgeThread]:
    """每条成功抽取的笔记 = 一条知识脉络（树上果实数按 tree_growth 单独计算）。"""
    try:
        result = await db.execute(
            select(Note)
            .where(Note.user_id == user_id, Note.status == NOTE_STATUS["SUCCESS"])
            .order_by(Note.upload_time.asc())
        )
        notes = result.scalars().all()
    except Exception:  # noqa: BLE001
        return []
    return [
        KnowledgeThread(
            note_id=note.id,
            title=note.title,
            nodes_count=note.nodes_count or 0,
            edges_count=note.edges_count or 0,
        )
        for note in notes
    ]


@router.get("/status", response_model=PetStatus)
async def get_pet_status(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
):
    pet = await pet_service.get_or_create_pet(db, user_id)

    knowledge_total = 0
    try:
        overview = await graph_service.get_mastery_overview(user_id)
        knowledge_total = int(overview.get("total", 0) or 0)
    except Exception:  # noqa: BLE001
        knowledge_total = 0

    threads = await _get_knowledge_threads(db, user_id)

    medals = pet_service.compute_medals(pet.total_harvested or 0)
    next_tier = pet_service.next_medal(pet.total_harvested or 0)

    # 以「知识点总数」为唯一事实来源同步树木状态，幂等且可无损处理溢出：
    # 历史/种子数据直接写入 notes 表、未经抽取流程，这里会据其补齐；
    # 已收割的成长值经 tree_growth_consumed 扣除，保证同一批知识不被重复结算。
    total_nodes = sum(t.nodes_count for t in threads)
    earned_cycles = max(0, int(total_nodes)) // pet_service.KNOWLEDGE_FOR_FULL
    progress, ready_cycles = pet_service.derive_growth(
        total_nodes, pet.tree_growth_consumed or 0.0
    )
    if (
        (pet.growth_cycles or 0) != earned_cycles
        or abs((pet.tree_growth or 0.0) - progress) > 1e-6
    ):
        pet.growth_cycles = earned_cycles
        pet.tree_growth = progress
        await db.commit()
        await db.refresh(pet)

    # 展示口径：存在可收割轮次时，进度显示为满额（100），驱动前端成熟态与果实渲染。
    display_growth = 100.0 if ready_cycles > 0 else progress

    # 主动关怀：每日首次访问时，宠物主动开口问候
    greeting = pet_service.take_daily_care(pet)
    if greeting is not None:
        await db.commit()

    return PetStatus(
        level=pet.level,
        exp=pet.exp,
        exp_max=pet_service.exp_max(pet.level),
        fruits=pet.fruits,
        tree_growth=display_growth,
        tree_stage=_tree_stage(display_growth),
        harvestable_cycles=ready_cycles,
        name=pet.name,
        species=pet.species,
        color=pet.color,
        personality=pet.personality,
        knowledge_total=knowledge_total,
        tree_fruits=len(threads),
        threads=threads,
        total_harvested=pet.total_harvested or 0,
        medal=pet_service.current_medal_id(pet.total_harvested or 0),
        medals=[PetMedal(**m) for m in medals],
        next_medal=next_tier["id"] if next_tier else None,
        next_medal_threshold=next_tier["threshold"] if next_tier else None,
        voice_preset=pet.voice_preset,
        mood=pet_service.compute_mood(pet),
        bond=pet_service.effective_bond(pet),
        bond_level=pet_service.bond_level(pet_service.effective_bond(pet)),
        streak_days=pet.streak_days or 0,
        greeting=greeting,
    )


@router.post("/voice", response_model=PetVoiceResult)
async def set_pet_voice(
    body: PetVoiceRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """保存用户的宠物音色预设（账号级，跨设备同步）。"""
    if body.voice_preset not in pet_service.VOICE_PRESETS:
        raise HTTPException(status_code=400, detail="不支持的音色预设")
    pet = await _get_or_create_pet(db, user_id)
    pet.voice_preset = body.voice_preset
    await db.commit()
    await db.refresh(pet)
    return PetVoiceResult(voice_preset=pet.voice_preset)


@router.post("/harvest", response_model=HarvestResult)
async def harvest(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    pet = await _get_or_create_pet(db, user_id)
    # 原子条件更新：存在「已满额但未收割」的成长轮次时结算一次，避免并发重复收割或刷分。
    # 兼容历史数据：旧行的 tree_growth 直接为 100（未经 growth_cycles 拆分）也允许收割。
    result = await db.execute(
        update(Pet)
        .where(
            Pet.user_id == user_id,
            or_(
                Pet.growth_cycles * 100 > func.coalesce(Pet.tree_growth_consumed, 0.0),
                Pet.tree_growth >= 100,
            ),
        )
        .values(
            fruits=func.coalesce(Pet.fruits, 0) + pet_service.MAX_TREE_FRUITS,
            total_harvested=func.coalesce(Pet.total_harvested, 0)
            + pet_service.MAX_TREE_FRUITS,
            tree_growth_consumed=func.coalesce(Pet.tree_growth_consumed, 0.0) + 100.0,
            # 仅清空旧行的满额显示值；新模型下 tree_growth 为当前轮进度，需保留。
            tree_growth=case((Pet.tree_growth >= 100, 0.0), else_=Pet.tree_growth),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=400, detail="树木尚未成熟，无法收取果实")

    await db.commit()
    await db.refresh(pet)

    # 收到果实 = 一次强正向互动：切换为兴奋情绪并显著提升亲密度
    pet_service.apply_event(pet, "harvest")
    await db.commit()
    await db.refresh(pet)

    harvested = pet_service.MAX_TREE_FRUITS
    medal_after = pet_service.current_medal_id(pet.total_harvested or 0)
    medal_before = pet_service.current_medal_id((pet.total_harvested or 0) - harvested)

    ready_cycles = max(
        0,
        (pet.growth_cycles or 0) - int((pet.tree_growth_consumed or 0.0) // 100),
    )
    return HarvestResult(
        fruits=pet.fruits,
        tree_growth=100.0 if ready_cycles > 0 else pet.tree_growth,
        harvested=harvested,
        total_harvested=pet.total_harvested or 0,
        medal=medal_after,
        new_medal=medal_after if medal_after != medal_before else None,
        harvestable_cycles=ready_cycles,
    )


@router.post("/feed", response_model=FeedResult)
async def feed(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_or_create_pet(db, user_id)
    # 原子预占一颗果实：并发投喂时只有一个请求能扣减成功，避免果实扣成负数
    result = await db.execute(
        update(Pet)
        .where(Pet.user_id == user_id, Pet.fruits > 0)
        .values(fruits=Pet.fruits - 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=400, detail="没有果实可投喂")

    pet = (await db.execute(select(Pet).where(Pet.user_id == user_id))).scalar_one()
    # 投喂只提供经验（升级反馈），不再直接抬升树木成长值：
    # 树木成长严格由知识点驱动，避免投喂污染成长曲线的反解基准。
    pet.exp += pet_service.FEED_EXP_GAIN

    leveled_up = False
    while pet.exp >= pet_service.exp_max(pet.level):
        pet.exp -= pet_service.exp_max(pet.level)
        pet.level += 1
        leveled_up = True

    # 投喂是一次正向互动：切换为开心情绪并提升亲密度
    pet_service.apply_event(pet, "feed")
    await db.commit()
    await db.refresh(pet)

    ready_cycles = max(
        0,
        (pet.growth_cycles or 0) - int((pet.tree_growth_consumed or 0.0) // 100),
    )
    display_growth = 100.0 if ready_cycles > 0 else pet.tree_growth
    return FeedResult(
        level=pet.level,
        exp=pet.exp,
        exp_max=pet_service.exp_max(pet.level),
        tree_growth=display_growth,
        tree_stage=_tree_stage(display_growth),
        leveled_up=leveled_up,
    )

async def _get_knowledge_concepts(graph_service: GraphService, user_id: str) -> list[str]:
    try:
        graph_data = await graph_service.get_user_graph(user_id)
        nodes = graph_data.get("nodes", []) if graph_data else []
        return [n.get("name", "") for n in nodes if n.get("name")]
    except Exception:
        return []


@router.post("/chat")
async def pet_chat(
    body: PetChatRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_ai_service),
    graph_service: GraphService = Depends(get_graph_service),
):
    pet = await _get_or_create_pet(db, user_id)
    # 对话是一次互动：记录互动时间、维持连续打卡（不改变成长）
    pet_service.apply_event(pet, "chat")
    await db.commit()

    knowledge_concepts = []
    if pet.level >= 3:
        knowledge_concepts = await _get_knowledge_concepts(graph_service, user_id)

    # 载入最近若干轮对话作为上下文；结合情绪注入个性化人设
    history = await pet_service.load_recent_messages(db, user_id)
    mood = pet_service.compute_mood(pet)

    async def stream():
        collected: list[str] = []
        try:
            async for token in ai_service.pet_chat_stream(
                level=pet.level,
                user_message=body.message,
                knowledge_concepts=knowledge_concepts,
                name=pet.name,
                personality=pet.personality,
                species=pet.species,
                mood=mood,
                history=history,
            ):
                collected.append(token)
                yield f"data: {token}\n\n"
        except LLM_ERROR_TYPES as exc:
            logger.warning("宠物对话调用 LLM 失败，触发降级：%s", exc)
            yield f"data: {AI_BUSY_MESSAGE}\n\n"
        yield "data: [DONE]\n\n"
        # 流式结束后持久化本轮对话，供下一次多轮上下文使用
        try:
            await pet_service.save_chat_exchange(
                db, user_id, body.message, "".join(collected).strip()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("保存宠物对话记忆失败：%s", exc)

    return StreamingResponse(stream(), media_type="text/event-stream")
