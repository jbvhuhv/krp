import json as _json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_ai_service, get_current_user_id, get_graph_service
from app.core.logger import get_logger
from app.schemas.brainstorm import (
    BrainstormNode,
    SuggestRequest,
    SuggestResponse,
    VerifyIssue,
    VerifyRequest,
    VerifyResponse,
)
from app.services.ai_service import AIService
from app.services.graph_service import GraphService

router = APIRouter()

logger = get_logger(__name__)

MAX_OUTLINE_LINES = 120
MAX_OUTLINE_DEPTH = 6

_CATEGORY_ALIASES = {
    "category",
    "categories",
    "group",
    "chapter",
    "section",
    "目录",
    "分类",
    "章节",
    "单元",
    "模块",
    "分组",
}
_KNOWLEDGE_ALIASES = {
    "knowledge",
    "concept",
    "fact",
    "skill",
    "method",
    "point",
    "知识点",
    "概念",
    "事实",
    "技能",
    "方法",
    "要点",
}


def _normalize_node_type(data: dict) -> str:
    has_children = bool(data.get("children"))
    for key in ("node_type", "type"):
        raw = str(data.get(key) or "").strip().lower()
        if raw in _CATEGORY_ALIASES:
            return "category"
        if raw in _KNOWLEDGE_ALIASES:
            return "category" if has_children else "knowledge"
    return "category" if has_children else "knowledge"


def _node_tag(node: dict) -> str:
    return "目录" if node.get("node_type") == "category" else "知识点"


def _build_outline(book: dict, nodes: list[dict], root_id: str | None = None) -> str:
    children: dict[str | None, list[dict]] = {}
    for node in nodes:
        children.setdefault(node.get("parent_id"), []).append(node)

    id_to_node = {n.get("id"): n for n in nodes}
    lines: list[str] = []

    def walk(parent_id: str | None, depth: int) -> None:
        if len(lines) >= MAX_OUTLINE_LINES or depth > MAX_OUTLINE_DEPTH:
            return
        for child in children.get(parent_id, []):
            lines.append(f"{'  ' * depth}- [{_node_tag(child)}] {child.get('name', '')}")
            walk(child.get("id"), depth + 1)

    if root_id and root_id in id_to_node:
        node = id_to_node[root_id]
        lines.append(f"[{_node_tag(node)}] {node.get('name', '')}")
        walk(root_id, 1)
    else:
        lines.append(f"书名：{book.get('name', '')}")
        walk(book.get("id"), 0)
    return "\n".join(lines)


def _to_node(data: dict) -> BrainstormNode:
    if not isinstance(data, dict):
        data = {}
    node_type = _normalize_node_type(data)
    raw_children = data.get("children") or []
    return BrainstormNode(
        name=str(data.get("name", "")).strip() or "未命名",
        summary=str(data.get("summary", "") or ""),
        node_type=node_type,
        type=str(data.get("type", "concept") or "concept"),
        reason=str(data.get("reason", "") or ""),
        parent_name=str(data.get("parent_name", "") or ""),
        children=[_to_node(c) for c in raw_children if isinstance(c, dict)],
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_structure(
    payload: VerifyRequest,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
    ai_service: AIService = Depends(get_ai_service),
):
    data = await graph_service.get_tree(user_id, payload.book_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在"
        )

    nodes = data["nodes"]
    if payload.node_id and not any(n.get("id") == payload.node_id for n in nodes):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在"
        )

    outline = _build_outline(data["book"], nodes, payload.node_id)
    result = await ai_service.verify_structure(outline)
    if result.get("status") == "failed":
        return VerifyResponse(status="failed", message=result.get("message", ""))

    name_to_id = {n.get("name"): n.get("id") for n in nodes}
    issues = []
    for item in result.get("issues", []):
        if not isinstance(item, dict):
            continue
        node_name = str(item.get("node_name") or item.get("name") or "")
        issues.append(
            VerifyIssue(
                node_id=name_to_id.get(node_name),
                node_name=node_name,
                status=str(item.get("status", "error") or "error"),
                reason=str(item.get("reason", "") or ""),
            )
        )
    missing = [_to_node(m) for m in result.get("missing", []) if isinstance(m, dict)]
    return VerifyResponse(
        status="ok",
        overall=str(result.get("overall", "") or ""),
        issues=issues,
        missing=missing,
    )


@router.post("/suggest", response_model=SuggestResponse)
async def suggest(
    payload: SuggestRequest,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
    ai_service: AIService = Depends(get_ai_service),
):
    node = await graph_service.get_node_detail(user_id, payload.node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在"
        )

    node_name = node.get("name", "")
    node_summary = node.get("summary", "")

    if payload.mode == "generate":
        result = await ai_service.generate_subtree(node_name, node_summary)
        if result.get("status") == "failed":
            return SuggestResponse(
                status="failed", message=result.get("message", ""), mode="generate"
            )
        return SuggestResponse(
            status="ok",
            mode="generate",
            subtree=[_to_node(n) for n in result.get("nodes", []) if isinstance(n, dict)],
        )

    user_idea = (payload.user_idea or "").strip()
    if user_idea:
        result = await ai_service.guide_idea(node_name, user_idea)
        if result.get("status") == "failed":
            return SuggestResponse(status="failed", message=result.get("message", ""))
        return SuggestResponse(
            status="ok",
            mode="hint",
            guidance=str(result.get("guidance", "") or ""),
        )

    result = await ai_service.suggest_hint(node_name, node_summary)
    if result.get("status") == "failed":
        return SuggestResponse(status="failed", message=result.get("message", ""))
    return SuggestResponse(
        status="ok",
        mode="hint",
        suggestions=[
            _to_node(n) for n in result.get("suggestions", []) if isinstance(n, dict)
        ],
    )

def _json_default(obj: object) -> object:
    """SSE 载荷的兜底序列化。

    曾经这里直接 `json.dumps(payload)`，而 suggestions 里放的是 pydantic 模型
    `BrainstormNode`，于是 hint 分支必然抛
    `TypeError: Object of type BrainstormNode is not JSON serializable`：
    异常发生在 StreamingResponse 已经开始发送之后，客户端只拿到半截流，
    用户看到的是「暂无建议」，模型算出的结果被静默丢弃。
    """
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return str(obj)


def _sse(payload: dict) -> str:
    return f"data: {_json.dumps(payload, ensure_ascii=False, default=_json_default)}\n\n"


@router.post("/suggest/stream")
async def suggest_stream(
    payload: SuggestRequest,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
    ai_service: AIService = Depends(get_ai_service),
):
    # 流式接口只覆盖 hint / guide 两条路径（都是文本增量）。
    # generate 返回的是结构化子树，一次性 JSON 更合适，走 /brainstorm/suggest。
    # 这里显式拒绝而不是静默当成 hint——否则调用方以为拿到了子树，实际拿到一堆名字。
    if payload.mode == "generate":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="流式构思不支持 mode=generate，请改用 /brainstorm/suggest",
        )

    node = await graph_service.get_node_detail(user_id, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")

    node_name = node.get("name", "")
    node_summary = node.get("summary", "")
    user_idea = (payload.user_idea or "").strip()

    async def event_source():
        # 注意：流一旦开始发送，状态码就已经是 200，后续任何异常都无法再改成 5xx。
        # 因此每个分支都必须自己兜住异常并补一帧 done，否则客户端会停在「加载中」。
        # 同时错误文案对客户端一律泛化，详细堆栈只进日志，避免把内部实现细节泄给前端。
        if user_idea:
            yield _sse({"type": "start", "mode": "guide"})
            try:
                async for delta in ai_service.guide_idea_stream(node_name, user_idea):
                    yield _sse({"type": "delta", "content": delta})
            except Exception as exc:  # noqa: BLE001 - 已在流中，只能降级为错误帧
                logger.warning("[BRAINSTORM] 引导流式中断: %s", exc, exc_info=True)
                yield _sse({"type": "error", "message": "生成中断，请重试"})
            yield _sse({"type": "done"})
            return

        yield _sse({"type": "start", "mode": "hint"})
        try:
            result = await ai_service.suggest_hint(node_name, node_summary)
            if result.get("status") == "failed":
                yield _sse({"type": "error", "message": result.get("message", "")})
                yield _sse({"type": "done"})
                return
            suggestions = [
                _to_node(n) for n in result.get("suggestions", []) if isinstance(n, dict)
            ]
            yield _sse({"type": "suggestions", "suggestions": suggestions})
        except Exception as exc:  # noqa: BLE001 - 同上，保证流有终止帧
            logger.warning("[BRAINSTORM] 提示流式生成失败: %s", exc, exc_info=True)
            yield _sse({"type": "error", "message": "构思生成失败，请重试"})
        yield _sse({"type": "done"})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        # 关掉反向代理的缓冲，否则 Nginx/Caddy 会把分块攒起来再发，失去流式效果
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
