# 单服务镜像：一个容器同时提供后端 API 与前端页面（适合 Render 免费档等单服务托管）
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
# 演示构建开关：置 true 时登录框会显示一个可直接登录的演示账号，
# 方便评委/体验者立刻看到完整示例数据。普通构建不传这三个参数即可。
ARG VITE_DEMO_MODE=true
ARG VITE_DEMO_PHONE=13900000001
ARG VITE_DEMO_CODE=123456
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
EXPOSE 8000
# 平台（Render 等）会注入 PORT；本地未设置时退回 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
