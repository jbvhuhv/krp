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
    # 是否对外暴露 Swagger / ReDoc / OpenAPI。
    # 默认关闭：演示环境常常 DEBUG=true，此时若不单独控制，/docs 会把完整接口面公开给公网。
    # 本地要看文档在 backend/.env 里显式设 ENABLE_API_DOCS=true。
    ENABLE_API_DOCS: bool = False
    # 显式放行「弱 SECRET_KEY」的逃生阀，默认 false。
    # 为什么需要它：以前弱密钥只在 DEBUG=false 时才拦，而演示环境（含 docker-compose.prod.yml）
    # 为了保住万能码登录把 DEBUG 设成了 true —— 于是 .env.production 里原样留着
    # 「请替换为随机字符串」也能正常启动，等于 JWT 密钥可被猜中、任意 token 可伪造。
    # 现在改成「与 DEBUG 解耦」：弱密钥一律拒绝启动，只有显式打开本开关才放行。
    # 本地开发在 backend/.env 设 true；生产/演示环境不要设。
    ALLOW_WEAK_SECRET: bool = False

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
    # 结构化输出：抽取与评分要求模型返回 JSON 对象。上游不支持 response_format 时会自动
    # 退化为纯文本调用（见 MaasProvider.chat），因此默认开启即可安全上线。
    LLM_JSON_MODE: bool = True

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
    # 访客聊天（公开 WebSocket）的用量闸门：这是唯一不需要登录就能触发的 LLM 入口，
    # 没有约束时任何人可以对已发布分身无限提问，直接烧掉模型额度。
    VISITOR_CHAT_MAX_PER_MINUTE: int = 20
    VISITOR_CHAT_MAX_CHARS: int = 500
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
    # 每用户 24 小时内可上传的笔记数。每次上传都会触发一次（失败重试 3 次）LLM 抽取，
    # 缺这道闸门时单个账号即可无限刷量——这是目前最大的成本敞口。
    UPLOAD_DAILY_LIMIT: int = 20
    ALLOWED_EXTENSIONS: list[str] = [
        ".md", ".markdown", ".txt", ".pdf",
        ".doc", ".docx",
    ]
    IMAGE_EXTENSIONS: list[str] = [".png", ".jpg", ".jpeg"]

    SMS_CODE_TTL: int = 300
    SMS_RATE_LIMIT_INTERVAL: int = 60
    SMS_DAILY_LIMIT: int = 5
    # 登录失败次数限制（同一手机号在窗口期内允许的最大失败次数）
    LOGIN_MAX_FAILURES: int = 10
    LOGIN_FAILURE_WINDOW_SECONDS: int = 600
    # 开发万能验证码：必须由环境变量显式提供，不再内置默认值。
    # 留空即视为禁用（即使 ALLOW_DEV_LOGIN=true 也无法用万能码登录）。
    SMS_DEV_MASTER_CODE: str = ""
    # 是否允许使用开发万能验证码登录（须同时 DEBUG=true 才生效）。
    # 生产环境必须保持 False；本地开发在 backend/.env 显式设 ALLOW_DEV_LOGIN=true。
    ALLOW_DEV_LOGIN: bool = False
    # 万能验证码**允许登录的手机号白名单**（英文逗号分隔，留空 = 任何手机号都不能用万能码）。
    # 必须收紧到白名单：否则任何人只要知道对方手机号，就能用一把公开的万能码登录对方账号。
    # 这里刻意用 str 而非 list[str]：pydantic-settings 对 list 类型按 JSON 解析，
    # 运维在 .env 里写 13900000001,13900000002 会直接启动失败，字符串更不容易踩坑。
    DEV_LOGIN_PHONE_ALLOWLIST: str = ""

    # 演示数据自动引导：数据库/图谱为空时，自动灌入随仓库分发的演示数据（backend/demo/）。
    # 让"克隆即可运行、部署即有内容"成立；置 false 可关闭。已存在数据时绝不做任何改动。
    DEMO_BOOTSTRAP: bool = True

    # 前端构建产物目录：存在 index.html 时由后端直接托管，实现单服务部署。
    # 留空则自动探测 FRONTEND_DIST 常见位置（../frontend/dist、./frontend_dist）。
    FRONTEND_DIST: str = ""

    # 知识图谱后端：auto = Neo4j 不可用时退回内置只读演示图谱；neo4j = 仅用 Neo4j；sqlite = 强制内置
    GRAPH_BACKEND: str = "auto"

    def dev_login_allowlist(self) -> set[str]:
        """解析万能码白名单（兼容中文逗号与空格，便于手写 .env）。"""
        raw = self.DEV_LOGIN_PHONE_ALLOWLIST.replace("，", ",")
        return {item.strip() for item in raw.split(",") if item.strip()}


DEFAULT_WELCOME_MESSAGE = "你好！我是你的专属知识分身，欢迎向我提问。"


settings = Settings()

# SECRET_KEY 强度校验：JWT 用 HS256 签名，密钥就是全部安全性。
# 原实现只拦「完全等于 change-me-in-production」，于是 change-me-demo-only、
# change-me-<日期> 这类改一版的变体全部静默通过，很容易一路带进正式环境。
# 第二版把弱密钥与 DEBUG 解耦：只要弱就拒绝启动，靠 ALLOW_WEAK_SECRET 显式放行。
# 原因见 Settings.ALLOW_WEAK_SECRET 的注释——生产 compose 当前是 DEBUG=true，
# 若继续用 DEBUG 判断，占位密钥永远不会被拦住。
_MIN_SECRET_LEN = 32
# 明显是占位符/弱口令的字样：命中即视为「没配」
_BLOCKED_SECRET_MARKERS = (
    "change-me",
    "changeme",
    "change_me",
    "secret",
    "demo",
    "dev-only",
    "test-only",
    "请替换",
)
# 长度下限：低于此值一律视为未配置（16 位随机串 ≈ 96 bit，勉强可接受）
_HARD_MIN_SECRET_LEN = 16


def _secret_problem(secret: str) -> str:
    """返回不可接受的密钥原因；空串表示超出硬性底线。"""
    low = secret.lower()
    if any(marker in low for marker in _BLOCKED_SECRET_MARKERS):
        return "包含 change-me / secret / demo / 请替换 等占位字样"
    if len(secret) < _HARD_MIN_SECRET_LEN:
        return f"长度仅 {len(secret)} 位，至少需要 {_HARD_MIN_SECRET_LEN} 位"
    return ""


_secret_issue = _secret_problem(settings.SECRET_KEY)
if _secret_issue:
    if not settings.ALLOW_WEAK_SECRET:
        raise RuntimeError(
            f"SECRET_KEY 不合规：{_secret_issue}。JWT 用 HS256 签名，密钥就是全部安全性，"
            "占位密钥意味着任何人都能伪造登录态。请配置至少 32 位的强随机密钥："
            "python -c \"import secrets;print(secrets.token_urlsafe(48))\"；"
            "仅在本地开发确实无所谓时，才在 backend/.env 显式设 ALLOW_WEAK_SECRET=true。"
        )
    get_logger(__name__).warning(
        "当前 SECRET_KEY 不合规（%s），因 ALLOW_WEAK_SECRET=true 已放行；"
        "该开关只应在本地使用，部署前务必配置强随机 SECRET_KEY 并关掉它",
        _secret_issue,
    )
elif len(settings.SECRET_KEY) < _MIN_SECRET_LEN:
    # 能启动但偏短：不阻断（避免误伤线上已有部署），只提示尽快换掉
    get_logger(__name__).warning(
        "SECRET_KEY 长度 %d 偏短，建议使用至少 %d 位的随机密钥",
        len(settings.SECRET_KEY),
        _MIN_SECRET_LEN,
    )

# 强制关闭「万能验证码」：仅当 DEBUG=true 且显式配置了非空 SMS_DEV_MASTER_CODE 时才允许。
# 这样即使部署时误留 ALLOW_DEV_LOGIN=true，生产环境（DEBUG=false）也不会出现登录绕过。
if settings.ALLOW_DEV_LOGIN and not (settings.DEBUG and settings.SMS_DEV_MASTER_CODE):
    get_logger(__name__).critical(
        "ALLOW_DEV_LOGIN 已被强制关闭：仅 DEBUG=true 且显式配置 SMS_DEV_MASTER_CODE 时生效"
    )
    settings.ALLOW_DEV_LOGIN = False

if settings.DEBUG and settings.ALLOW_DEV_LOGIN:
    if not settings.dev_login_allowlist():
        # 宁可不能用，也不能对全站开放：白名单为空时万能码完全不生效（见 auth.login）。
        get_logger(__name__).critical(
            "开发登录已开启，但 DEV_LOGIN_PHONE_ALLOWLIST 为空：万能验证码对所有手机号均不生效。"
            "如需演示登录，请把演示手机号写进该白名单"
        )
    else:
        get_logger(__name__).warning(
            "开发登录已启用（DEBUG=true + ALLOW_DEV_LOGIN=true）："
            "万能验证码仅对白名单手机号生效 %s，生产环境必须关闭",
            sorted(settings.dev_login_allowlist()),
        )


def get_postgres_url() -> str:
    if settings.POSTGRES_URL:
        return settings.POSTGRES_URL
    return (
        f"postgresql+psycopg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
