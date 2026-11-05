from fastapi import APIRouter, Depends, HTTPException, Query, status
from neo4j.exceptions import ServiceUnavailable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_current_user_id, get_db, get_graph_service
from app.core.logger import get_logger
from app.core.prompt_manager import prompt_manager
from app.models.note import Note
from app.schemas.graph import (
    BookOut,
    BooksResponse,
    CategoryCreate,
    EdgeCreate,
    EdgeOut,
    GraphData,
    KnowledgeCreate,
    NodeCreate,
    NodeOut,
    NodeSourceOut,
    NodeUpdate,
    NoteBrief,
    StudyProfileResponse,
    SubjectStatsResponse,
    TreeNodeOut,
    TreeResponse,
)
from app.services.ai_service import AIService
from app.services.graph_service import GraphService

router = APIRouter()
logger = get_logger(__name__)


def _empty_graph() -> GraphData:
    return GraphData(nodes=[], edges=[])


def _build_tree(nodes: list[dict]) -> list[TreeNodeOut]:
    by_id = {n["id"]: n for n in nodes}
    children_map: dict[str, list[TreeNodeOut]] = {}
    roots: list[TreeNodeOut] = []

    for n in nodes:
        parent_id = n.get("parent_id")
        node = TreeNodeOut(
            id=n["id"],
            name=n.get("name", ""),
            summary=n.get("summary", ""),
            node_type=n.get("node_type", "knowledge"),
            parent_id=parent_id,
            mastery=n.get("mastery", 0.0),
            origin=n.get("origin", "user"),
            x=n.get("x"),
            y=n.get("y"),
            children=[],
        )
        if parent_id and parent_id in by_id:
            children_map.setdefault(parent_id, []).append(node)
        elif not parent_id or parent_id not in by_id:
            roots.append(node)

    visiting: set[str] = set()

    def attach_children(parent: TreeNodeOut):
        if parent.id in visiting:
            parent.children = []
            return
        visiting.add(parent.id)
        parent.children = children_map.get(parent.id, [])
        for child in parent.children:
            attach_children(child)

    for root in roots:
        attach_children(root)
    return roots


async def _inherit_from_parent(
    graph_service: GraphService,
    user_id: str,
    parent_id: str | None,
    subject: str | None,
    source_note_id: str | None,
) -> tuple[str | None, str | None]:
    if not parent_id or (subject is not None and source_note_id is not None):
        return subject, source_note_id
    parent = await graph_service.get_node_detail(user_id, parent_id)
    if not parent:
        return subject, source_note_id
    if subject is None:
        subject = parent.get("subject")
    if source_note_id is None:
        source_note_id = parent.get("source_note_id")
    return subject, source_note_id


@router.get("/books", response_model=BooksResponse)
async def get_books(
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    try:
        books = await graph_service.get_books(user_id)
    except ServiceUnavailable:
        return BooksResponse(items=[])
    return BooksResponse(items=[BookOut(**b) for b in books])


@router.get("/tree/{book_id}", response_model=TreeResponse)
async def get_tree(
    book_id: str,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    data = await graph_service.get_tree(user_id, book_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="书籍不存在")
    book = BookOut(**data["book"])
    tree = _build_tree(data["nodes"])
    edges = [EdgeOut(**e) for e in data["edges"]]
    return TreeResponse(book=book, tree=tree, edges=edges)


@router.post("/nodes", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: NodeCreate,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    node_id = await graph_service.create_node(
        user_id=user_id,
        name=payload.name,
        summary=payload.summary,
        type=payload.type,
        source_note_id=payload.source_note_id,
        subject=payload.subject,
        node_type=payload.node_type,
        parent_id=payload.parent_id,
        origin=payload.origin,
        x=payload.x,
        y=payload.y,
    )
    return NodeOut(
        id=node_id,
        name=payload.name,
        summary=payload.summary,
        type=payload.type,
        subject=payload.subject,
        node_type=payload.node_type,
        parent_id=payload.parent_id,
        source_note_id=payload.source_note_id,
        origin=payload.origin,
        x=payload.x,
        y=payload.y,
    )


@router.post("/categories", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    subject, source_note_id = await _inherit_from_parent(
        graph_service, user_id, payload.parent_id, payload.subject, payload.source_note_id
    )
    node_id = await graph_service.create_node(
        user_id=user_id,
        name=payload.name,
        summary=payload.summary,
        type="category",
        source_note_id=source_note_id,
        subject=subject,
        node_type="category",
        parent_id=payload.parent_id,
        origin=payload.origin,
        x=payload.x,
        y=payload.y,
    )
    return NodeOut(
        id=node_id,
        name=payload.name,
        summary=payload.summary,
        type="category",
        subject=subject,
        node_type="category",
        parent_id=payload.parent_id,
        source_note_id=source_note_id,
        origin=payload.origin,
        x=payload.x,
        y=payload.y,
    )


@router.post("/knowledge", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    payload: KnowledgeCreate,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    subject, source_note_id = await _inherit_from_parent(
        graph_service, user_id, payload.parent_id, payload.subject, payload.source_note_id
    )
    node_id = await graph_service.create_node(
        user_id=user_id,
        name=payload.name,
        summary=payload.summary,
        type=payload.type,
        source_note_id=source_note_id,
        subject=subject,
        node_type="knowledge",
        parent_id=payload.parent_id,
        origin=payload.origin,
        x=payload.x,
        y=payload.y,
    )
    return NodeOut(
        id=node_id,
        name=payload.name,
        summary=payload.summary,
        type=payload.type,
        subject=subject,
        node_type="knowledge",
        parent_id=payload.parent_id,
        source_note_id=source_note_id,
        origin=payload.origin,
        x=payload.x,
        y=payload.y,
    )


@router.put("/nodes/{node_id}", response_model=NodeOut)
async def update_node(
    node_id: str,
    payload: NodeUpdate,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
    db: AsyncSession = Depends(get_db),
):
    if payload.parent_id is not None and await graph_service.is_descendant(
        user_id, node_id, payload.parent_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="父节点不能是自身或其子孙节点",
        )

    updated = await graph_service.update_node(
        user_id=user_id,
        node_id=node_id,
        name=payload.name,
        summary=payload.summary,
        type=payload.type,
        subject=payload.subject,
        node_type=payload.node_type,
        parent_id=payload.parent_id,
        origin=payload.origin,
        x=payload.x,
        y=payload.y,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="节点不存在",
        )

    # 知识书改名时，同步来源笔记的标题，保持两侧一致
    if (
        payload.name
        and payload.name.strip()
        and updated.get("node_type") == "book"
        and updated.get("source_note_id")
    ):
        note = await db.get(Note, updated["source_note_id"])
        if note is not None and note.user_id == user_id:
            note.title = payload.name.strip()
            await db.commit()

    return NodeOut(**updated)


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: str,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    deleted = await graph_service.delete_subtree(user_id=user_id, node_id=node_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="节点不存在",
        )


@router.post("/edges", response_model=EdgeOut, status_code=status.HTTP_201_CREATED)
async def create_edge(
    payload: EdgeCreate,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    edge_id = await graph_service.create_edge(
        user_id=user_id,
        source_id=payload.source_id,
        target_id=payload.target_id,
        relation=payload.relation,
        weight=payload.weight,
    )
    if edge_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="源节点或目标节点不存在",
        )
    return EdgeOut(
        id=edge_id,
        source_id=payload.source_id,
        target_id=payload.target_id,
        relation=payload.relation,
        weight=payload.weight,
    )


@router.get("/nodes/{node_id}/source", response_model=NodeSourceOut)
async def get_node_source(
    node_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
):
    node = await graph_service.get_node_detail(user_id=user_id, node_id=node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="节点不存在",
        )
    source_note = None
    source_note_id = node.get("source_note_id")
    if source_note_id:
        result = await db.execute(
            select(Note).where(Note.id == source_note_id, Note.user_id == user_id)
        )
        note = result.scalar_one_or_none()
        if note:
            source_note = NoteBrief(
                id=note.id,
                title=note.title,
                format=note.format,
                content=note.content,
            )
    return NodeSourceOut(node_id=node_id, source_note=source_note)


@router.post("/nodes/{node_id}/ai-summary")
async def generate_ai_summary(
    node_id: str,
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
    ai_service: AIService = Depends(get_ai_service),
):
    node = await graph_service.get_node_detail(user_id=user_id, node_id=node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")

    children = await graph_service.get_children(user_id=user_id, parent_id=node_id)
    child_info = "、".join(
        [f"{c['name']}（{c.get('summary', '')}）" for c in children[:20]]
    )

    if node.get("node_type") == "category":
        prompt = prompt_manager.get_category_summary_prompt(
            node_name=node["name"],
            child_info=child_info,
        )
    else:
        prompt = prompt_manager.get_node_summary_prompt(
            node_name=node["name"],
            node_summary=node.get("summary", "无"),
            child_info=child_info,
        )

    try:
        summary = await ai_service.llm.chat(prompt)
        summary = summary.strip().strip('"').strip('"').strip('"')
    except Exception as e:
        # 不回显上游异常内容（可能含上游地址、配额信息），只记日志并返回通用提示
        logger.exception("[GRAPH] 节点摘要生成失败 node_id=%s", node_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 生成失败，请稍后重试",
        ) from e

    return {"summary": summary}


@router.get("/subject-stats", response_model=SubjectStatsResponse)
async def get_subject_stats(
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    try:
        stats = await graph_service.get_subject_stats(user_id)
    except ServiceUnavailable:
        return SubjectStatsResponse(items=[])
    return SubjectStatsResponse(items=stats)


@router.get("/study-profile", response_model=StudyProfileResponse)
async def get_study_profile(
    user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    """学习画像六维：掌握度/熟练度/巩固度/复习覆盖/知识广度/知识体量。"""
    try:
        profile = await graph_service.get_study_profile(user_id)
    except ServiceUnavailable:
        return StudyProfileResponse(total=0, dimensions=[])
    return StudyProfileResponse(**profile)


@router.get("/{user_id}", response_model=GraphData)
async def get_graph(
    user_id: str,
    subject: str | None = Query(None, description="按学科过滤"),
    note_id: str | None = Query(None, description="按来源笔记过滤"),
    current_user_id: str = Depends(get_current_user_id),
    graph_service: GraphService = Depends(get_graph_service),
):
    if user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问他人图谱",
        )
    try:
        data = await graph_service.get_user_graph(
            user_id, subject=subject, note_id=note_id
        )
    except ServiceUnavailable:
        return _empty_graph()
    return GraphData(
        nodes=[NodeOut(**n) for n in data["nodes"]],
        edges=[EdgeOut(**e) for e in data["edges"]],
    )
