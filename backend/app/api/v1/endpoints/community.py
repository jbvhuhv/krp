import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from neo4j.exceptions import ServiceUnavailable
from sqlalchemy import case, delete, select, update
from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db, get_graph_service, get_optional_user_id
from app.core import moderation
from app.core.config import settings
from app.core.logger import get_logger
from app.core.upload_guard import read_upload_limited
from app.models.community import (
    CommunityComment,
    CommunityLike,
    CommunityPost,
    CommunityPostView,
)
from app.models.user import User
from app.schemas.community import (
    AuthorInfo,
    CommentCreate,
    CommentList,
    CommentOut,
    ForkResponse,
    GraphSnapshot,
    GraphSnapshotEdge,
    GraphSnapshotNode,
    LikeResponse,
    PostBrief,
    PostCreate,
    PostList,
    PostOut,
    PostVisibilityUpdate,
    SubjectCount,
)
from app.services.graph.constants import NODE_TYPE_BOOK
from app.services.graph_service import GraphService
from app.services.notification_service import NotificationService

router = APIRouter()
logger = get_logger(__name__)


def _ensure_clean(*fields: str | None) -> None:
    """广场内容初筛：命中内置/自定义违规词直接拒绝，不把命中词回显给用户。"""
    hit = moderation.find_violation(*fields)
    if hit:
        logger.warning("[UGC] 内容命中违规词 word=%s", hit)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="内容包含违规信息，请修改后再发布",
        )

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_COVER_SIZE = 5 * 1024 * 1024
# 热度排序（Hacker News 风格重力模型）：
# hot = 互动量 / (发布时长(小时) + 2)^gravity，让新鲜的高互动内容能压过老帖
HOT_GRAVITY = 1.5
HOT_LIKE_WEIGHT = 3
# 热度排序时参与计算的最大候选集，避免全表加载（重力排序本身近似全局）
HOT_CANDIDATE_WINDOW = 500
_MAGIC_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def _utcnow() -> datetime:
    """当前 UTC 时间（naive），与数据库 naive 存储口径一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _age_hours(created_at: datetime | None, now: datetime) -> float:
    if created_at is None:
        return 0.0
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    return max(0.0, (now - created_at).total_seconds() / 3600.0)


def _hot_score(post: CommunityPost, now: datetime) -> float:
    engagement = (post.likes_count or 0) * HOT_LIKE_WEIGHT + (post.views_count or 0)
    return engagement / ((_age_hours(post.created_at, now) + 2.0) ** HOT_GRAVITY)



def _detect_image_ext(header: bytes) -> str | None:
    for sig, ext in _MAGIC_SIGNATURES:
        if header.startswith(sig):
            return ext
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    return None


def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return "匿名用户"
    return phone[:3] + "****" + phone[-4:]


def _display_name(user: User | None) -> str:
    if user is None:
        return "匿名用户"
    return user.nickname or _mask_phone(user.phone)


async def _build_author(db: AsyncSession, user_id: str) -> AuthorInfo:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    return AuthorInfo(user_id=user_id, nickname=_display_name(user))


async def notify_post_author(
    db: AsyncSession,
    post: CommunityPost,
    actor_user_id: str,
    notif_type: str,
    title: str,
    content: str,
) -> None:
    """给帖子作者推送互动通知；自己操作自己不通知，失败不影响主流程。

    ``title`` 传入的是不含主语的动作短语（如「评论了你的知识图谱」），
    这里统一补上互动者的显示名，作者才知道「是谁」——原来的硬编码「有人」
    让通知完全无法判断该不该回应，也点不出社交线索。
    """
    if post is None or post.user_id == actor_user_id:
        return
    try:
        actor = await _build_author(db, actor_user_id)
        await NotificationService(db).create(
            user_id=post.user_id,
            title=f"{actor.nickname} {title}"[:255],
            content=content,
            type=notif_type,
            # 让前端能「点通知直接跳到对应帖子」
            target_type="post",
            target_id=post.id,
        )
    except Exception:  # noqa: BLE001 - 通知失败不能影响点赞/评论主流程，但必须留痕
        logger.warning(
            "社区通知写入失败 post_id=%s type=%s", post.id, notif_type, exc_info=True
        )


def _derive_snapshot_meta(post: CommunityPost) -> tuple[str | None, int, int, str]:
    """从图谱快照派生列表卡片所需的元信息。

    - subject: 节点 subject 的众数，兜底取首个标签
    - node_count / edge_count: 快照中的知识点与关系数量
    - summary: 优先帖子简介，为空时由节点摘要拼接兜底
    """
    snapshot = post.graph_snapshot or {}
    nodes = snapshot.get("nodes", []) or []
    edges = snapshot.get("edges", []) or []

    subject_counts: dict[str, int] = {}
    for node in nodes:
        subj = (node or {}).get("subject")
        if subj:
            subject_counts[subj] = subject_counts.get(subj, 0) + 1
    if subject_counts:
        subject = max(subject_counts, key=subject_counts.get)
    else:
        tags = post.tags or []
        subject = tags[0] if tags else None

    summary = (post.description or "").strip()
    if not summary:
        parts = [
            (node or {}).get("summary", "")
            for node in nodes[:3]
        ]
        summary = " · ".join(p for p in parts if p)

    return subject, len(nodes), len(edges), summary


async def _build_brief(
    db: AsyncSession, post: CommunityPost, current_user_id: str | None = None
) -> PostBrief:
    author = await _build_author(db, post.user_id)
    liked = False
    if current_user_id:
        like_result = await db.execute(
            select(CommunityLike).where(
                CommunityLike.user_id == current_user_id,
                CommunityLike.post_id == post.id,
            )
        )
        liked = like_result.scalar_one_or_none() is not None
    subject, node_count, edge_count, summary = _derive_snapshot_meta(post)
    return PostBrief(
        id=post.id,
        user_id=post.user_id,
        title=post.title,
        description=post.description,
        summary=summary,
        subject=subject,
        node_count=node_count,
        edge_count=edge_count,
        cover_url=post.cover_url,
        tags=post.tags or [],
        likes_count=post.likes_count,
        clones_count=post.clones_count,
        views_count=post.views_count,
        is_public=post.is_public,
        created_at=post.created_at,
        author=author,
        liked=liked,
    )


async def _build_briefs(
    db: AsyncSession, posts: list[CommunityPost], current_user_id: str | None = None
) -> list[PostBrief]:
    """批量构建列表卡片，避免逐条查询作者与点赞状态（N+1）。"""
    if not posts:
        return []

    user_ids = {post.user_id for post in posts}
    users = (
        await db.execute(select(User).where(User.id.in_(user_ids)))
    ).scalars().all()
    user_map = {user.id: user for user in users}

    liked_ids: set[str] = set()
    if current_user_id:
        post_ids = [post.id for post in posts]
        liked_rows = await db.execute(
            select(CommunityLike.post_id).where(
                CommunityLike.user_id == current_user_id,
                CommunityLike.post_id.in_(post_ids),
            )
        )
        liked_ids = {row[0] for row in liked_rows}

    briefs: list[PostBrief] = []
    for post in posts:
        user = user_map.get(post.user_id)
        author = AuthorInfo(
            user_id=post.user_id,
            nickname=_display_name(user),
        )
        subject, node_count, edge_count, summary = _derive_snapshot_meta(post)
        briefs.append(
            PostBrief(
                id=post.id,
                user_id=post.user_id,
                title=post.title,
                description=post.description,
                summary=summary,
                subject=subject,
                node_count=node_count,
                edge_count=edge_count,
                cover_url=post.cover_url,
                tags=post.tags or [],
                likes_count=post.likes_count,
                clones_count=post.clones_count,
                views_count=post.views_count,
                is_public=post.is_public,
                created_at=post.created_at,
                author=author,
                liked=post.id in liked_ids,
            )
        )
    return briefs


@router.get("/posts", response_model=PostList)
async def list_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None, description="按标签过滤"),
    q: str | None = Query(None, max_length=50, description="按标题/简介/标签/学科搜索"),
    subject: str | None = Query(None, max_length=50, description="按学科筛选"),
    sort: str = Query("newest", pattern="^(newest|hottest)$"),
    current_user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
):
    base_query = select(CommunityPost).where(CommunityPost.is_public.is_(True))
    offset = (page - 1) * size

    q_kw = (q or "").strip().lower()
    needs_python_filter = bool(q_kw) or bool(tag) or bool(subject)
    if needs_python_filter:
        # tags / subject 派生自 JSON 快照：SQLite 下中文被转义成 \uXXXX，
        # SQL LIKE 不可靠，所以关键词、标签、学科任一存在时统一在 Python 端过滤。
        # 本项目演示规模（几十帖）下全量加载成本可忽略；规模上来再换全文索引。
        result = await db.execute(base_query)
        all_posts = []
        for post in result.scalars().all():
            post_subject = _derive_snapshot_meta(post)[0] or ""
            if subject and post_subject != subject:
                continue
            if tag and tag not in (post.tags or []):
                continue
            if q_kw:
                tags_text = " ".join(str(t) for t in (post.tags or [])).lower()
                haystack = (
                    f"{post.title or ''}\n{post.description or ''}\n{tags_text}\n{post_subject}"
                ).lower()
                if q_kw not in haystack:
                    continue
            all_posts.append(post)
        if sort == "hottest":
            now = _utcnow()
            all_posts.sort(key=lambda p: _hot_score(p, now), reverse=True)
        else:
            all_posts.sort(key=lambda p: p.created_at, reverse=True)
        total = len(all_posts)
        paged_posts = all_posts[offset : offset + size]
    else:
        # 无过滤条件时下推到数据库，避免全表加载 + 内存分页
        total = (
            await db.execute(
                select(sa_func.count()).select_from(base_query.order_by(None).subquery())
            )
        ).scalar_one()
        if sort == "hottest":
            # 取互动量最高的有限候选集后按时间衰减重排，保证新鲜高互动内容优先
            candidates = (
                await db.execute(
                    base_query.order_by(
                        (
                            CommunityPost.likes_count * HOT_LIKE_WEIGHT
                            + CommunityPost.views_count
                        ).desc(),
                        CommunityPost.created_at.desc(),
                    ).limit(HOT_CANDIDATE_WINDOW)
                )
            ).scalars().all()
            now = _utcnow()
            ranked = sorted(candidates, key=lambda p: _hot_score(p, now), reverse=True)
            paged_posts = ranked[offset : offset + size]
        else:
            paged_posts = (
                await db.execute(
                    base_query.order_by(CommunityPost.created_at.desc()).limit(size).offset(offset)
                )
            ).scalars().all()

    items = await _build_briefs(db, paged_posts, current_user_id)
    subjects = await _collect_subject_counts(db)
    return PostList(items=items, total=total, subjects=subjects)


async def _collect_subject_counts(db: AsyncSession) -> list[SubjectCount]:
    """全站公开帖子的学科分布（数量降序）。
    subject 派生自 JSON 快照（SQLite 下中文转义，SQL 聚合不可靠），
    演示规模下全量扫描成本可忽略；规模上来后快照应落独立列再聚合。"""
    result = await db.execute(
        select(CommunityPost).where(CommunityPost.is_public.is_(True))
    )
    counts: dict[str, int] = {}
    for post in result.scalars().all():
        subject = _derive_snapshot_meta(post)[0]
        if subject:
            counts[subject] = counts.get(subject, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [SubjectCount(name=name, count=count) for name, count in ranked]


@router.get("/my-posts", response_model=PostList)
async def list_my_posts(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """当前用户发布的全部帖子（含已撤回），按发布时间倒序。"""
    total = (
        await db.execute(
            select(sa_func.count())
            .select_from(CommunityPost)
            .where(CommunityPost.user_id == user_id)
        )
    ).scalar_one()
    offset = (page - 1) * size
    result = await db.execute(
        select(CommunityPost)
        .where(CommunityPost.user_id == user_id)
        .order_by(CommunityPost.created_at.desc())
        .limit(size)
        .offset(offset)
    )
    posts = list(result.scalars().all())
    items = await _build_briefs(db, posts, user_id)
    return PostList(items=items, total=total)


@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: str,
    current_user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    # 撤回（is_public=false）的帖子对其他人一律 404，不泄露存在性；
    # 但作者本人必须能读到——否则「我的发布」里点进去白屏，也没法再改回公开。
    is_owner = post is not None and current_user_id == post.user_id
    if post is None or (not post.is_public and not is_owner):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

    # 浏览量口径：作者查看自己的帖子不计；登录用户同一帖子 24 小时内只计一次；
    # 未登录访客无法稳定识别，照常计数。
    should_count = False
    dirty = False
    now = _utcnow()
    if not current_user_id:
        should_count = True
    elif current_user_id != post.user_id:
        view = (
            await db.execute(
                select(CommunityPostView).where(
                    CommunityPostView.post_id == post_id,
                    CommunityPostView.user_id == current_user_id,
                )
            )
        ).scalar_one_or_none()
        if view is None:
            db.add(
                CommunityPostView(
                    post_id=post_id, user_id=current_user_id, viewed_at=now
                )
            )
            should_count = True
            dirty = True
        else:
            last_viewed = view.viewed_at
            if last_viewed is not None and last_viewed.tzinfo is not None:
                last_viewed = last_viewed.astimezone(timezone.utc).replace(tzinfo=None)
            if last_viewed is None or (now - last_viewed) >= timedelta(hours=24):
                should_count = True
                # 只有真的计数时才刷新时间戳：窗口锚定在「首次查看」，
                # 也避免读接口每个请求都持一次写锁（SQLite 下会与抽取写入互相阻塞）。
                view.viewed_at = now
                dirty = True

    if should_count:
        await db.execute(
            update(CommunityPost)
            .where(CommunityPost.id == post_id)
            .values(views_count=CommunityPost.views_count + 1)
        )
        dirty = True

    if dirty:
        await db.commit()

    brief = await _build_brief(db, post, current_user_id)
    snapshot = GraphSnapshot(
        nodes=[GraphSnapshotNode(**n) for n in (post.graph_snapshot or {}).get("nodes", [])],
        edges=[GraphSnapshotEdge(**e) for e in (post.graph_snapshot or {}).get("edges", [])],
    )
    return PostOut(**brief.model_dump(), graph_snapshot=snapshot)


@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: PostCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_clean(payload.title, payload.description, " ".join(payload.tags or []))
    post = CommunityPost(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        graph_snapshot=payload.graph_snapshot.model_dump(),
        tags=payload.tags,
        cover_url=payload.cover_url,
        is_public=payload.is_public,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    brief = await _build_brief(db, post, user_id)
    return PostOut(**brief.model_dump(), graph_snapshot=payload.graph_snapshot)


@router.post("/posts/{post_id}/visibility", response_model=PostBrief)
async def set_post_visibility(
    post_id: str,
    payload: PostVisibilityUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """撤销曝光（is_public=false）或重新公开（is_public=true）自己发布的帖子。"""
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    if post.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="只能操作自己发布的帖子"
        )

    post.is_public = payload.is_public
    await db.commit()
    await db.refresh(post)
    return await _build_brief(db, post, user_id)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """彻底删除自己发布的帖子（不可恢复），同时清理其点赞与评论记录。"""
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    if post.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="只能删除自己发布的帖子"
        )

    await db.execute(delete(CommunityLike).where(CommunityLike.post_id == post_id))
    await db.execute(delete(CommunityComment).where(CommunityComment.post_id == post_id))
    await db.execute(delete(CommunityPost).where(CommunityPost.id == post_id))
    await db.commit()
    return None


@router.get("/posts/{post_id}/comments", response_model=CommentList)
async def list_comments(
    post_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(200, ge=1, le=500),
    current_user_id: str | None = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    # 与详情接口同一口径：撤回帖只有作者本人能读到评论。
    is_owner = post is not None and current_user_id == post.user_id
    if post is None or (not post.is_public and not is_owner):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

    rows = await db.execute(
        select(CommunityComment)
        .where(CommunityComment.post_id == post_id)
        .order_by(CommunityComment.created_at.desc())
    )
    all_comments = list(rows.scalars().all())

    children: dict[str, list[str]] = {}
    for c in all_comments:
        if c.parent_id:
            children.setdefault(c.parent_id, []).append(c.id)
    live_ids = {c.id for c in all_comments if not c.is_deleted}

    def _has_live_descendant(comment_id: str) -> bool:
        stack = list(children.get(comment_id, []))
        while stack:
            current = stack.pop()
            if current in live_ids:
                return True
            stack.extend(children.get(current, []))
        return False

    visible = [
        c
        for c in all_comments
        if (not c.is_deleted) or _has_live_descendant(c.id)
    ]
    total = len(visible)
    offset = (page - 1) * size
    comments = visible[offset : offset + size]

    user_map: dict[str, User] = {}
    user_ids = {c.user_id for c in comments}
    if user_ids:
        users = (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars().all()
        user_map = {u.id: u for u in users}

    items = [
        CommentOut(
            id=c.id,
            post_id=c.post_id,
            user_id=c.user_id,
            content="该评论已被删除" if c.is_deleted else c.content,
            parent_id=c.parent_id,
            is_deleted=c.is_deleted,
            created_at=c.created_at,
            author=AuthorInfo(
                user_id=c.user_id,
                nickname="已删除" if c.is_deleted else _display_name(user_map.get(c.user_id)),
            ),
        )
        for c in comments
    ]
    return CommentList(items=items, total=total)


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    post_id: str,
    payload: CommentCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None or not post.is_public:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

    content = payload.content.strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="评论内容不能为空"
        )
    _ensure_clean(content)

    parent_id = payload.parent_id
    if parent_id:
        parent = (
            await db.execute(
                select(CommunityComment).where(CommunityComment.id == parent_id)
            )
        ).scalar_one_or_none()
        if parent is None or parent.post_id != post_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="被回复的评论不存在"
            )


    comment = CommunityComment(
        post_id=post_id, user_id=user_id, content=content, parent_id=parent_id
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    await notify_post_author(
        db,
        post,
        user_id,
        "comment",
        "评论了你的知识图谱",
        f"评论了你的知识图谱《{post.title}》：{content[:60]}",
    )

    return CommentOut(
        id=comment.id,
        post_id=comment.post_id,
        user_id=comment.user_id,
        content=comment.content,
        parent_id=comment.parent_id,
        created_at=comment.created_at,
        author=await _build_author(db, user_id),
    )


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除自己发表的评论（软删除，保留他人回复）。"""
    result = await db.execute(
        select(CommunityComment).where(CommunityComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    if comment is None or comment.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论不存在")
    if comment.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="只能删除自己的评论"
        )

    comment.is_deleted = True
    await db.commit()
    return None


@router.post("/cover", status_code=status.HTTP_201_CREATED)
async def upload_cover(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    # 分块读取并在超限时中断，避免超大上传把内存打满
    content = await read_upload_limited(file, MAX_COVER_SIZE)
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 PNG / JPG / JPEG / WEBP / GIF 格式",
        )
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="文件类型不是图片"
        )

    real_ext = _detect_image_ext(content[:16])
    if real_ext is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="文件内容不是有效图片"
        )

    cover_dir = os.path.join(settings.UPLOAD_DIR, "covers")
    os.makedirs(cover_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{real_ext}"
    with open(os.path.join(cover_dir, fname), "wb") as f:
        f.write(content)

    return {"url": f"/uploads/covers/{fname}"}


@router.post("/posts/{post_id}/like", response_model=LikeResponse)
async def toggle_like(
    post_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None or not post.is_public:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

    like_result = await db.execute(
        select(CommunityLike).where(
            CommunityLike.user_id == user_id,
            CommunityLike.post_id == post_id,
        )
    )
    existing_like = like_result.scalar_one_or_none()

    if existing_like:
        await db.execute(
            delete(CommunityLike).where(CommunityLike.id == existing_like.id)
        )
        await db.execute(
            update(CommunityPost)
            .where(CommunityPost.id == post_id)
            .values(
                likes_count=case(
                    (CommunityPost.likes_count > 0, CommunityPost.likes_count - 1),
                    else_=0,
                )
            )
        )
        await db.commit()
        await db.refresh(post)
        return LikeResponse(liked=False, likes_count=post.likes_count)

    db.add(CommunityLike(user_id=user_id, post_id=post_id))
    try:
        await db.execute(
            update(CommunityPost)
            .where(CommunityPost.id == post_id)
            .values(likes_count=CommunityPost.likes_count + 1)
        )
        await db.commit()
    except IntegrityError:
        # 并发重复点赞：由唯一约束兜底，视为已点赞且不重复计数
        await db.rollback()
        count_row = await db.execute(
            select(CommunityPost.likes_count).where(CommunityPost.id == post_id)
        )
        return LikeResponse(liked=True, likes_count=count_row.scalar_one_or_none() or 0)
    await db.refresh(post)
    await notify_post_author(
        db,
        post,
        user_id,
        "like",
        "赞了你的知识图谱",
        f"赞了你的知识图谱《{post.title}》",
    )
    return LikeResponse(liked=True, likes_count=post.likes_count)


async def _cleanup_fork_nodes(
    graph_service: GraphService, user_id: str, node_ids: list[str]
) -> None:
    """克隆失败时尽力回收已创建的孤立节点（DETACH DELETE 幂等）。"""
    for node_id in reversed(node_ids):
        try:
            await graph_service.delete_node(user_id, node_id)
        except Exception:  # noqa: BLE001 - 回收本身失败只记账，不能掩盖原始异常
            logger.warning("回滚克隆节点失败 node_id=%s", node_id, exc_info=True)
            continue


def _dominant_subject(raw_nodes: list[dict]) -> str | None:
    """从快照节点中取出现次数最多的学科，用于补建的书根节点。"""
    counts: dict[str, int] = {}
    for node in raw_nodes:
        subject = (node.get("subject") or "").strip()
        if subject:
            counts[subject] = counts.get(subject, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


@router.post("/posts/{post_id}/fork", response_model=ForkResponse)
async def fork_post(
    post_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
):
    result = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None or not post.is_public:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")

    snapshot = post.graph_snapshot or {}
    raw_nodes = snapshot.get("nodes", [])
    raw_edges = snapshot.get("edges", [])

    if not raw_nodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="图谱快照为空，无法克隆",
        )

    fork_origin = f"fork:{post_id}"
    if await graph_service.count_nodes_by_origin(user_id, fork_origin) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="你已克隆过该图谱，无需重复克隆",
        )

    created_node_ids: list[str] = []
    # 与书架 node_count 对齐：只统计书根之下的分类/知识点，
    # 否则 fork 返回数会比书架显示多 1（书根节点），用户会以为克隆丢了内容。
    created_non_book_count = 0
    try:
        old_to_new = {}
        for node in raw_nodes:
            is_book = node.get("node_type") == NODE_TYPE_BOOK
            new_id = await graph_service.create_node(
                user_id=user_id,
                # 书根用帖子标题命名：克隆提示说的是《帖子标题》，
                # 沿用原书文件名（如 persona_A_note.md）会让用户对不上号
                name=post.title if is_book else node.get("name", "未命名"),
                summary=(post.description or "") if is_book else node.get("summary", ""),
                type=node.get("type", "concept"),
                source_note_id=None,
                subject=node.get("subject"),
                node_type=node.get("node_type", "knowledge"),
                parent_id=None,
                origin=fork_origin,
            )
            old_to_new[node.get("id")] = new_id
            created_node_ids.append(new_id)
            if not is_book:
                created_non_book_count += 1

        # 回填层级：parent_id 指向快照内其它节点时恢复 CHILD_OF 关系
        for node in raw_nodes:
            old_parent = node.get("parent_id")
            new_id = old_to_new.get(node.get("id"))
            if old_parent and old_parent in old_to_new and new_id:
                await graph_service.link_parent(user_id, new_id, old_to_new[old_parent])

        # 兜底：快照缺少 book 根节点时，为无归属节点补建书根节点，
        # 否则克隆结果不会出现在「我的知识书架」，表现为“克隆成功却看不到”
        book_new_ids = [
            old_to_new[n.get("id")]
            for n in raw_nodes
            if n.get("node_type") == NODE_TYPE_BOOK and n.get("id") in old_to_new
        ]
        orphan_new_ids = [
            old_to_new[n.get("id")]
            for n in raw_nodes
            if n.get("node_type") != NODE_TYPE_BOOK
            and n.get("id") in old_to_new
            and not (n.get("parent_id") and n.get("parent_id") in old_to_new)
        ]
        if orphan_new_ids:
            if not book_new_ids:
                book_new_id = await graph_service.create_node(
                    user_id=user_id,
                    name=post.title,
                    summary=post.description or "",
                    type=NODE_TYPE_BOOK,
                    subject=_dominant_subject(raw_nodes),
                    node_type=NODE_TYPE_BOOK,
                    origin=fork_origin,
                )
                created_node_ids.append(book_new_id)
                book_new_ids = [book_new_id]
            for orphan_id in orphan_new_ids:
                await graph_service.link_parent(user_id, orphan_id, book_new_ids[0])

        # 关系边：按快照 edges 重建并返回真实创建数量
        edges_created = 0
        for edge in raw_edges:
            source_new = old_to_new.get(edge.get("source_id"))
            target_new = old_to_new.get(edge.get("target_id"))
            if source_new and target_new:
                await graph_service.create_edge(
                    user_id=user_id,
                    source_id=source_new,
                    target_id=target_new,
                    relation=edge.get("relation", "related_to"),
                    weight=edge.get("weight", 1.0),
                )
                edges_created += 1

        await db.execute(
            update(CommunityPost)
            .where(CommunityPost.id == post_id)
            .values(clones_count=CommunityPost.clones_count + 1)
        )
        await db.commit()

        await notify_post_author(
            db,
            post,
            user_id,
            "fork",
            "克隆了你的知识图谱",
            f"克隆了你的知识图谱《{post.title}》",
        )

        return ForkResponse(
            message=f"克隆成功，《{post.title}》已加入你的知识书架",
            nodes_count=created_non_book_count,
            edges_count=edges_created,
        )
    except ServiceUnavailable as exc:
        await _cleanup_fork_nodes(graph_service, user_id, created_node_ids)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识图谱服务不可用，无法克隆",
        ) from exc
    except Exception:
        # 跨存储（Neo4j + SQL）无法真正原子，失败时尽力回收已创建节点
        await _cleanup_fork_nodes(graph_service, user_id, created_node_ids)
        raise
