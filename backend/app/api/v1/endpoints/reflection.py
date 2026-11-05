from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user_id, get_reflection_service
from app.core.exceptions import ServiceUnavailableException
from app.schemas.reflection import (
    AnswerSubmit,
    FeedbackOut,
    MasteryTrend,
    MasteryTrendItem,
    NodeMasteryDetail,
    ReflectionHistory,
    ReflectionHistoryItem,
    ReflectionQuestion,
    ScheduleOut,
    ScheduleUpdate,
)
from app.services.providers.base import AI_BUSY_MESSAGE
from app.services.reflection_service import ReflectionService, _generate_lock

router = APIRouter()


def _to_question_out(q) -> ReflectionQuestion:
    return ReflectionQuestion(
        id=q.id,
        question=q.question,
        target_node_id=q.target_node_id,
        node_name=q.node_name,
        answered=q.answer is not None,
        reason=q.reason,
        generated_by=q.generated_by,
    )



@router.get("/today", response_model=list[ReflectionQuestion])
async def get_today_questions(
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    questions = await reflection_service.get_today_questions(user_id)
    return [
        _to_question_out(q)
        for q in questions
    ]


@router.post("/today/generate", response_model=list[ReflectionQuestion])
async def generate_today_questions(
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    async with _generate_lock(user_id):
        existing = await reflection_service.get_today_questions(user_id)
        if existing:
            questions = existing
        else:
            questions = await reflection_service.generate_questions(user_id)
    return [
        _to_question_out(q)
        for q in questions
    ]


@router.post("/answer", response_model=FeedbackOut)
async def submit_answer(
    payload: AnswerSubmit,
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    result = await reflection_service.evaluate_answer(
        user_id=user_id,
        question_id=payload.question_id,
        answer=payload.answer,
        is_voice=payload.is_voice,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="反思问题不存在",
        )
    if result.get("status") == "failed":
        raise ServiceUnavailableException(result.get("message") or AI_BUSY_MESSAGE)
    return FeedbackOut(**result)


@router.get("/history", response_model=ReflectionHistory)
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    data = await reflection_service.get_history(user_id, limit=limit, offset=offset)
    return ReflectionHistory(
        items=[
            ReflectionHistoryItem(
                id=item.id,
                question=item.question,
                answer=item.answer,
                feedback=item.feedback,
                mastery_score=item.mastery_score,
                target_node_id=item.target_node_id,
                node_name=item.node_name,
                is_voice=item.is_voice,
                created_at=item.created_at,
                answered_at=item.answered_at,
            )
            for item in data["items"]
        ],
        total=data["total"],
    )


@router.get("/mastery", response_model=MasteryTrend)
async def get_mastery(
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    data = await reflection_service.get_mastery_trend(user_id)
    return MasteryTrend(
        nodes=[MasteryTrendItem(**node) for node in data["nodes"]],
        timeline=data["timeline"],
    )


@router.get("/nodes/{node_id}/mastery", response_model=NodeMasteryDetail)
async def get_node_mastery_detail(
    node_id: str,
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    """某个知识点的掌握度溯源：当前值 + 每次反思的账（改前/改后/权重）。"""
    data = await reflection_service.get_node_mastery_detail(user_id, node_id)
    if not data["timeline"] and not data["node_name"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识点不存在，或还没有反思记录",
        )
    return NodeMasteryDetail(**data)


@router.get("/schedule", response_model=ScheduleOut)
async def get_schedule(
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    schedule = await reflection_service.get_schedule(user_id)
    return ScheduleOut(
        id=schedule.id,
        user_id=schedule.user_id,
        frequency=schedule.frequency,
        time_window=schedule.time_window,
        updated_at=schedule.updated_at,
    )


@router.put("/schedule", response_model=ScheduleOut)
async def update_schedule(
    payload: ScheduleUpdate,
    user_id: str = Depends(get_current_user_id),
    reflection_service: ReflectionService = Depends(get_reflection_service),
):
    schedule = await reflection_service.update_schedule(
        user_id=user_id,
        frequency=payload.frequency,
        time_window=payload.time_window,
    )
    return ScheduleOut(
        id=schedule.id,
        user_id=schedule.user_id,
        frequency=schedule.frequency,
        time_window=schedule.time_window,
        updated_at=schedule.updated_at,
    )
