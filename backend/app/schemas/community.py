from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class GraphSnapshotNode(BaseModel):
    id: str
    name: str
    summary: str = ""
    type: str = "concept"
    subject: str | None = None
    mastery: float = 0.0
    parent_id: str | None = None
    node_type: str | None = None


class GraphSnapshotEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation: str = "related_to"
    weight: float = 1.0


class GraphSnapshot(BaseModel):
    nodes: list[GraphSnapshotNode] = []
    edges: list[GraphSnapshotEdge] = []


class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=2000)
    graph_snapshot: GraphSnapshot
    tags: list[str] = Field(default=[], max_length=20)
    cover_url: str | None = None
    is_public: bool = True


class PostVisibilityUpdate(BaseModel):
    is_public: bool


class AuthorInfo(BaseModel):
    user_id: str
    nickname: str
    avatar: str | None = None


class PostBrief(BaseModel):
    id: str
    user_id: str
    title: str
    description: str
    summary: str = ""
    subject: str | None = None
    node_count: int = 0
    edge_count: int = 0
    cover_url: str | None = None
    tags: list[str] = []
    likes_count: int = 0
    clones_count: int = 0
    views_count: int = 0
    is_public: bool = True
    created_at: UtcDateTime
    author: AuthorInfo
    liked: bool = False


class PostOut(PostBrief):
    graph_snapshot: GraphSnapshot


class PostList(BaseModel):
    items: list[PostBrief]
    total: int


class LikeResponse(BaseModel):
    liked: bool
    likes_count: int


class ForkResponse(BaseModel):
    message: str
    nodes_count: int
    edges_count: int

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    parent_id: str | None = None


class CommentOut(BaseModel):
    id: str
    post_id: str
    user_id: str
    content: str
    parent_id: str | None = None
    is_deleted: bool = False
    created_at: UtcDateTime
    author: AuthorInfo


class CommentList(BaseModel):
    items: list[CommentOut]
    total: int
