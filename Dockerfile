# 单服务镜像：一个容器同时提供后端 API 与前端页面（适合单机单服务部署）
#
# 构建：docker build -t krp .
# 运行：docker run -p 8000:8000 -e DEBUG=true -e ALLOW_DEV_LOGIN=true -e SECRET_KEY=xxx krp
#
# 说明：
#   - 前端在阶段 1 用 Node 构建，产物拷进运行镜像，由 FastAPI 直接托管（同源，无跨域问题）
#   - 镜像内不含 .env / 本地数据库（见 .dockerignore），配置一律通过环境变量注入
#   - 首次启动时若数据库为空，会自动灌入 backend/demo/ 里的演示数据（可用 DEMO_BOOTSTRAP=false 关闭）

# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS frontend-build
WORKDIR /web
# 免费实例内存有限，限制 Node 堆大小，避免构建被 OOM 杀掉
ENV NODE_OPTIONS=--max-old-space-size=1024
# 演示构建开关：默认关闭。开启后登录框会显示可直接登录的演示账号，
# 等价于把一组可用凭据公开到前端产物里，仅限临时演示构建显式传参开启。
ARG VITE_DEMO_MODE=false
ARG VITE_DEMO_PHONE=
ARG VITE_DEMO_CODE=
ENV VITE_DEMO_MODE=$VITE_DEMO_MODE \
    VITE_DEMO_PHONE=$VITE_DEMO_PHONE \
    VITE_DEMO_CODE=$VITE_DEMO_CODE
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段 2：运行后端 ----------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=frontend-build /web/dist ./frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist

# 最小权限：创建固定的非 root 用户（UID/GID 10001）并预建数据目录。
# 说明：命名卷首次挂载时由 Docker 以 root 创建，因此升级到本版本前需要先把卷的所有者改为 10001。
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /data

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)"
# 平台/编排可能注入 PORT；本地未设置时退回 8000
# --proxy-headers：容器前面是宿主机 Caddy，不加这行访问日志与 request.client 全是 127.0.0.1，
# 按 IP 做的限流会退化成「全站一个桶」。端口只在 127.0.0.1 上发布（见 compose），
# 外部无法直连伪造 X-Forwarded-For，所以这里可以信任全部转发来源。
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
