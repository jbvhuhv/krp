from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_ai_service, get_current_user_id, get_graph_service
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
