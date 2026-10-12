from typing import Literal

from pydantic import BaseModel, Field


class BrainstormNode(BaseModel):
    name: str
    summary: str = ""
    node_type: str = "knowledge"
    type: str = "concept"
    reason: str = ""
    parent_name: str = ""
    children: list["BrainstormNode"] = []


BrainstormNode.model_rebuild()


class VerifyIssue(BaseModel):
    node_id: str | None = None
    node_name: str = ""
    status: str = "correct"
    reason: str = ""


class VerifyRequest(BaseModel):
    book_id: str
    node_id: str | None = None


class VerifyResponse(BaseModel):
    status: str = "ok"
    message: str = ""
    overall: str = ""
    issues: list[VerifyIssue] = []
    missing: list[BrainstormNode] = []


class SuggestRequest(BaseModel):
    book_id: str
    node_id: str
    mode: Literal["hint", "generate"] = "hint"
    user_idea: str | None = Field(default=None, max_length=2000)


class SuggestResponse(BaseModel):
    status: str = "ok"
    message: str = ""
    mode: str = "hint"
    guidance: str = ""
    suggestions: list[BrainstormNode] = []
    subtree: list[BrainstormNode] = []
