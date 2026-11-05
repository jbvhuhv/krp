from pydantic import BaseModel, Field


class NodeBase(BaseModel):
    name: str
    summary: str = ""
    type: str = "concept"
    subject: str | None = None
    node_type: str = "knowledge"
    parent_id: str | None = None
    origin: str = "user"
    x: float | None = None
    y: float | None = None


class NodeCreate(NodeBase):
    name: str = Field(..., min_length=1, max_length=200)
    source_note_id: str | None = None


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = None
    type: str | None = None
    subject: str | None = None
    node_type: str | None = None
    parent_id: str | None = None
    origin: str | None = None
    x: float | None = None
    y: float | None = None


class NodeOut(NodeBase):
    id: str
    mastery: float = 0.0
    source_note_id: str | None = None


class EdgeCreate(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=64)
    relation: str = Field("related_to", max_length=50)
    weight: float = Field(1.0, ge=0.0)


class EdgeOut(EdgeCreate):
    id: str


class GraphData(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class NoteBrief(BaseModel):
    id: str
    title: str
    format: str
    content: str = ""


class NodeSourceOut(BaseModel):
    node_id: str
    source_note: NoteBrief | None = None


class SubjectStat(BaseModel):
    subject: str
    node_count: int
    avg_mastery: float


class SubjectStatsResponse(BaseModel):
    items: list[SubjectStat]


class ProfileDimension(BaseModel):
    name: str
    value: float
    tip: str = ""


class StudyProfileResponse(BaseModel):
    total: int = 0
    dimensions: list[ProfileDimension] = []


class BookOut(BaseModel):
    id: str
    name: str
    summary: str = ""
    source_note_id: str | None = None
    node_count: int = 0


class BooksResponse(BaseModel):
    items: list[BookOut]


class TreeNodeOut(BaseModel):
    id: str
    name: str
    summary: str = ""
    node_type: str = "knowledge"
    parent_id: str | None = None
    mastery: float = 0.0
    origin: str = "user"
    x: float | None = None
    y: float | None = None
    children: list["TreeNodeOut"] = []


TreeNodeOut.model_rebuild()


class TreeResponse(BaseModel):
    book: BookOut
    tree: list[TreeNodeOut]
    edges: list[EdgeOut] = []


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    summary: str = ""
    parent_id: str | None = None
    subject: str | None = None
    source_note_id: str | None = None
    origin: str = "user"
    x: float | None = None
    y: float | None = None


class KnowledgeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    summary: str = ""
    type: str = "concept"
    parent_id: str | None = None
    subject: str | None = None
    source_note_id: str | None = None
    origin: str = "user"
    x: float | None = None
    y: float | None = None
