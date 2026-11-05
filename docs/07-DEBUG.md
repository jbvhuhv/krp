# 调试与故障排查指南

本文件汇总本地开发中常见故障的排查路径。

## 1. Neo4j 连不上

**症状**：后端日志出现 `neo4j.exceptions.ServiceUnavailable`，或图谱接口返回空、知识抽取后节点未写入。

**排查路径**：
- 确认 Neo4j 进程在运行：浏览器访问 `http://localhost:7474`，并确认 Bolt 端口 `7687` 已监听。
- 核对 `backend/.env`：`NEO4J_URI`（默认 `bolt://localhost:7687`）、`NEO4J_USER`、`NEO4J_PASSWORD`。
- 启动方式二选一：
  - 本机已有 `deps/` 运行时：`./scripts/start_neo4j.sh`（Windows：`scripts\start_neo4j.bat`）。deps 里那份不含官方 `bin/`，所以不能用 `neo4j start`，脚本内部是直接拉起 `org.neo4j.server.CommunityEntryPoint`。
  - 新克隆的仓库（没有 `deps/`）：`docker compose up -d neo4j`（仓库根目录需先建 `.env` 写入 `NEO4J_PASSWORD`）。
- **启动顺序**：先起 Neo4j 再起后端更省事。后端启动探测只做 2 次短重试（约 6 秒）就降级，剩下的交给后台自愈协程（每 30 秒重探一次）：恢复后除了把图谱后端切回 Neo4j，还会**补跑** `init_vector_index` / `init_property_indexes` / `bootstrap_neo4j` / `normalize_last_reviewed`，所以索引与演示数据会自己补齐，不用重启后端。
  - 验证方式：看日志出现「Neo4j 已恢复：索引与演示数据已完成补建/补导」，或 `SHOW INDEXES` 里出现 `knowledge_user_idx` / `knowledge_user_type_idx` / `knowledge_note_idx`。
  - 2026-11-05 之前的版本没有这一步，冷启动后索引会永久缺失，只能重启进程修复。
- 另注意：`deps/` 那份 `target/conf/neo4j.conf` 关闭了认证（`dbms.security.auth_enabled=false`），密码不参与校验；Docker 版才校验。两种环境的密码行为不同，排查时别混。
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

## 5. 登录返回 401「验证码错误或已过期」，但验证码确实是对的

**症状**：演示环境用 `123456` 登录，一直 401。

**排查路径**：
- 万能码生效需要 **三个条件同时满足**：`DEBUG=true`、`ALLOW_DEV_LOGIN=true`、
  `SMS_DEV_MASTER_CODE` 非空；任一不满足都会被静默降级。
- 第四个条件（2026-11 安全加固后新增）：登录手机号必须在 **`DEV_LOGIN_PHONE_ALLOWLIST`** 白名单内。
  该值为**空**时，万能码对所有手机号都不生效——这是刻意的安全默认值，
  防止"任意手机号 + 公开万能码 = 任意账号被接管"。
- 启动日志会直接说明当前状态：白名单为空时打印
  `开发登录已开启，但 DEV_LOGIN_PHONE_ALLOWLIST 为空`；配置正确时打印实际生效的白名单号码。
- 生产环境排查同样从日志看：只要出现 `ALLOW_DEV_LOGIN 已被强制关闭`，说明 `DEBUG` 或
  `SMS_DEV_MASTER_CODE` 没配好。

## 6. 启动直接报 `SECRET_KEY 不合规`（起不来）

**症状**：容器反复重启，日志最后一行是 `RuntimeError: SECRET_KEY 不合规：...`。

**原因**：JWT 用 HS256 签名，密钥就是全部安全性。只要密钥含
`change-me` / `secret` / `demo` / `请替换` 等字样，或短于 16 位，就会被判定为「没配」。
这条校验**与 `DEBUG` 无关**——演示环境为了保住万能码登录把 `DEBUG` 设成了 `true`，
早期版本因此在 `DEBUG=true` 时只告警不拦截，于是 `.env.production` 里原样留着
`SECRET_KEY=请替换为随机字符串` 也能跑起来，等于谁都能伪造登录态。

**处理**：
```bash
openssl rand -hex 32        # 生成后写进 .env.production
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```
本地开发确实无所谓时，在 `backend/.env` 显式设 `ALLOW_WEAK_SECRET=true` 放行；
**该开关不要出现在生产环境的任何配置文件里**。

## 7. Docker 部署时的环境变量优先级

- `docker-compose.yml` 的 backend 服务同时使用 `env_file: ./backend/.env` 和 `environment:`；
- 优先级：`environment:` > `env_file:` > Dockerfile ENV；
- 因此容器内 `NEO4J_URI=bolt://neo4j:7687`（compose 内网），覆盖 `backend/.env` 的 `bolt://localhost:7687`；
- **`NEO4J_PASSWORD` 未在 compose 覆盖，取自 `backend/.env`，必须与 neo4j 服务密码一致**；
- **`DEBUG` 在 `docker-compose.prod.yml` 里是 `true`**（演示态：短信通道未接通，靠白名单万能码登录）。
  真正的安全边界不再是 `DEBUG`，而是 `DEV_LOGIN_PHONE_ALLOWLIST`（只有名单内号码能用万能码）
  与 `ENABLE_API_DOCS=false`（接口面不公开）。接好真实短信后应整体改回 `false`。