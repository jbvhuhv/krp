from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.logger import get_logger

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "Knowledge Reflection Platform"
    # 项目版本号，需与 frontend/package.json 的 version 保持一致。
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    # 是否开发/调试模式。仅此模式下才允许使用万能验证码等开发便利能力。
    # 默认关闭：生产环境不显式配置即为安全态；本地开发在 backend/.env 里设 DEBUG=true。
    DEBUG: bool = False

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "krp"
    POSTGRES_URL: str = ""

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    # Redis 连接/读写超时（秒）。缓存不可用时快速失败，避免请求长时间挂起。
    REDIS_CONNECT_TIMEOUT: float = 1.5
    # 面向用户的本地时区偏移（小时）。宠物问候时段、每日关怀/连续打卡日界按此计算。
    TIMEZONE_OFFSET_HOURS: float = 8.0

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    ALGORITHM: str = "HS256"

    LLM_PROVIDER: str = "maas"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    MAAS_API_KEY: str = ""
    MAAS_BASE_URL: str = ""
    MAAS_MODEL: str = "pangu"
    MAAS_EMBEDDING_MODEL: str = "bge-m3"

    # 图片笔记 OCR：指向一个支持视觉的 OpenAI 兼容多模态模型端点。
    OCR_BASE_URL: str = ""
    OCR_API_KEY: str = ""
    OCR_MODEL: str = ""

    EMBEDDING_DIMENSION: int = 1024
    NEO4J_VECTOR_INDEX: str = "knowledge_node_embedding"

    AVATAR_SIMILARITY_THRESHOLD: float = 0.7
    AVATAR_KEYWORD_THRESHOLD: float = 0.2
    AVATAR_TOP_K: int = 5
    AVATAR_EMBED_BACKFILL_LIMIT: int = 200
    SHARE_BASE_URL: str = "http://localhost:5173"
    # 允许跨域的前端来源；生产通过环境变量 CORS_ORIGINS 覆盖为实际域名
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    SCHEDULER_ENABLED: bool = True
    REFLECTION_CRON_HOUR: int = 20
    REFLECTION_CRON_MINUTE: int = 0
    REFLECTION_DAILY_LIMIT: int = 5
    EXTRACTION_MAX_ATTEMPTS: int = 3
    EXTRACTION_BACKOFF_SECONDS: float = 2.0

    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS: list[str] = [
        ".md", ".markdown", ".txt", ".pdf",
        ".doc", ".docx",
    ]
    IMAGE_EXTENSIONS: list[str] = [".png", ".jpg", ".jpeg"]

    SMS_CODE_TTL: int = 300
    SMS_RATE_LIMIT_INTERVAL: int = 60
    SMS_DAILY_LIMIT: int = 5
    SMS_DEV_MASTER_CODE: str = "123456"
    # 是否允许使用开发万能验证码登录（须同时 DEBUG=true 才生效）。
    # 生产环境必须保持 False；本地开发在 backend/.env 显式设 ALLOW_DEV_LOGIN=true。
    ALLOW_DEV_LOGIN: bool = False

    # 演示数据自动引导：数据库/图谱为空时，自动灌入随仓库分发的演示数据（backend/demo/）。
    # 让"克隆即可运行、部署即有内容"成立；置 false 可关闭。已存在数据时绝不做任何改动。
    DEMO_BOOTSTRAP: bool = True

    # 前端构建产物目录：存在 index.html 时由后端直接托管，实现单服务部署（如 Render 免费档）。
    # 留空则自动探测 FRONTEND_DIST 常见位置（../frontend/dist、./frontend_dist）。
    FRONTEND_DIST: str = ""


DEFAULT_WELCOME_MESSAGE = "你好！我是你的专属知识分身，欢迎向我提问。"


settings = Settings()

if settings.SECRET_KEY == "change-me-in-production":
    if not settings.DEBUG:
        raise RuntimeError(
            "生产环境（DEBUG=false）必须通过环境变量 SECRET_KEY 配置强随机密钥，"
            "当前仍为不安全的默认值 change-me-in-production"
        )
    get_logger(__name__).warning(
        "当前使用不安全的默认 SECRET_KEY（仅限本地调试）；部署前务必配置强随机 SECRET_KEY"
    )

if settings.DEBUG and not settings.ALLOW_DEV_LOGIN:
    get_logger(__name__).info(
        "DEBUG=true 但 ALLOW_DEV_LOGIN=false：万能验证码登录未启用；"
        "本地如需免验证码登录请在 backend/.env 设 ALLOW_DEV_LOGIN=true"
    )


def get_postgres_url() -> str:
    if settings.POSTGRES_URL:
        return settings.POSTGRES_URL
    return (
        f"postgresql+psycopg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
