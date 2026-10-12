from pydantic import BaseModel, field_validator


class SendCodeRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        import re

        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v


class LoginRequest(BaseModel):
    phone: str
    code: str


class UserOut(BaseModel):
    id: str
    phone: str
    student_id: str | None = None
    nickname: str | None = None


class UserUpdate(BaseModel):
    nickname: str | None = None

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        if len(v) > 16:
            raise ValueError("昵称不能超过 16 个字符")
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
