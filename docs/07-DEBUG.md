# 调试与故障排查指南

本文件汇总本地开发中常见故障的排查路径。

## 1. Neo4j 连不上

**症状**：后端日志出现 `neo4j.exceptions.ServiceUnavailable`，或图谱接口返回空、知识抽取后节点未写入。

**排查路径**：
- 确认 Neo4j 进程在运行：浏览器访问 `http://localhost:7474`，并确认 Bolt 端口 `7687` 已监听。
- 核对 `backend/.env`：`NEO4J_URI`（默认 `bolt://localhost:7687`）、`NEO4J_USER`、`NEO4J_PASSWORD`。
- 启动命令见根 `README.md`「启动基础设施」（`deps/neo4j-build/` 下的 CommunityEntryPoint）。
- 图谱不可用时后端会优雅降级（不抛 500），但知识点不会写入图中；恢复 Neo4j 后需对相关笔记重新抽取。

## 2. MaaS API 超时 / 鉴权失败

**症状**：抽取、评分或对话返回「AI繁忙，请稍后重试」或 HTTP 503。

**排查路径**：
- 核对 `backend/.env` 的 `MAAS_API_KEY`、`MAAS_BASE_URL`、`MAAS_MODEL`、`MAAS_EMBEDDING_MODEL`；图片笔记若报错，另核对 `OCR_API_KEY`、`OCR_BASE_URL`、`OCR_MODEL`。
- 确认 `LLM_PROVIDER` 取值（`config.py` 与 `.env.example` 默认均为 `maas`）；Provider 抽象层见 `app/services/providers/`（当前 `openai_provider.py` 为预留空壳，调用会抛 `NotImplementedError`，实际使用 `maas_provider`）。
- 超时/HTTP 错误已做降级：知识抽取标记为 `failed`（可调用 re-extract 重试）、反思评分返回 503、对话返回错误事件或错误提示。
- 可用 `curl` 直接请求 MaaS 接口，区分「网络不通」与「Key/模型无效」。

## 3. 前端跨域（CORS）失败

**症状**：浏览器控制台报 CORS 错误，请求被拦截。

**排查路径**：
- 后端允许来源配置为 `CORS_ORIGINS`（见 `app/core/config.py`），默认包含 `http://localhost:5173` 与 `http://127.0.0.1:5173`。
- 开发环境 Vite 已将 `/api` 代理到 `http://localhost:8000`（`frontend/vite.config.js`），经代理的请求通常不涉及跨域。
- 若前端直连后端地址，需确保 `CORS_ORIGINS` 与实际访问源一致；修改后重启后端生效。

## 4. 流式对话中断（数字分身）与 SSE（宠物）

**症状**：数字分身对话中断、无流式返回；或宠物对话无逐字输出。

**排查路径**：
- 数字分身走 **WebSocket**：检查事件流是否符合预期 `welcome → sources → chunk → done`；确认反向代理正确转发 WebSocket upgrade（Vite / Nginx 需开启 `ws` 支持）；后端 WS 端点 `/api/v1/avatar/chat/{avatarId}`；鉴权失败会导致 WS 关闭，检查请求携带的 Token 是否有效。
- 宠物走 **SSE**（非 WebSocket）：端点为 `POST /api/v1/pet/chat`，返回 `text/event-stream`；确认代理未缓冲/未关闭长连接。

## 5. Docker 部署时的环境变量优先级

- `docker-compose.yml` 的 backend 服务同时使用 `env_file: ./backend/.env` 和 `environment:`；
- 优先级：`environment:` > `env_file:` > Dockerfile ENV；
- 因此容器内 `NEO4J_URI=bolt://neo4j:7687`（compose 内网），覆盖 `backend/.env` 的 `bolt://localhost:7687`；
- **`NEO4J_PASSWORD` 未在 compose 覆盖，取自 `backend/.env`，必须与 neo4j 服务密码一致**；
- **`DEBUG` 已在 compose 显式设为 `false`**，生产环境万能码后门关闭。