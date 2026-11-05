# Changelog

本项目所有值得记录的变更都会记录在此文件。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## Unreleased

### 2026-11-05 · 演示数据量纲与答题闭环

**演示数据（评委会直接看到的两个硬伤）**

- **掌握度量纲混用**：演示图谱里 `demo-radar-*` / `demo-success-*` 那批是 0–1 比例（0.8 = 80%），
  真实答题写回的是 0–100 分，应用统一按百分比解释。结果 555 个知识点里 554 个被判「薄弱」，
  知识画像平均掌握度只有 **0.3%**，每日反思的理由清一色「掌握度 0 分」。
  新增 `backend/scripts/refresh_demo_graph.py`：比例值 ×100，其余节点按节点 id 稳定哈希
  补一条「学期中段」的复习轨迹（全部 0 分同样看不出学过什么）。现在掌握度 42.4、
  熟练度 11.7%、复习覆盖 74.2%
- **「掌握度溯源」抽屉是空的**：演示库 10 条已答记录全部缺 `mastery_before/after/weight`，
  且其中 3 条 `mastery_score` 是 0–1 量纲（前端显示成 1%）。新增
  `backend/scripts/backfill_demo_ledger.py` 按应用公式回放账本，并让图谱终值与账本一致

**反思闭环**

- **演示模式答题不改掌握度**：只读图谱下 `update_mastery` 直接 403，用户答完题一切照旧，
  第二天还是同一批题。新增 `node_mastery_overrides` 覆盖层（本地库持久化），
  `LocalGraphService` 读时合并、写时落库，重启进程仍有效
- **复习队列改为间隔重复优先**：原来是 `ORDER BY mastery ASC`，0 分的新知识点长期霸占队列，
  学过的内容再也回不来。改为先按「距上次复习天数」倒序、再按掌握度升序；出题理由对新节点
  改说「还没有复习记录」而不是「掌握度 0 分」
- `_days_since` 支持 ISO 字符串：演示图谱里的时间是字符串，此前一律解析失败，
  「越久没复习权重越大」在演示环境从未生效

**隐私**

- 注销与数据导出补齐 `node_views` / `node_mastery_overrides`：看过哪些知识点、掌握度如何变化
  属于个人信息，此前注销后仍留在库里

**测试**

- 新增 `tests/test_demo_data_and_overlay.py`（演示数据量纲/分布、覆盖层回写与重启、账本完整性）
- 修复幂等用例的顺序断言：同一秒生成的多条记录 `created_at` 相同，按 id 兜底排序与插入顺序
  不一致，原断言约 50% 概率随机失败

### 2026-11-04 · 三轮体检修复（部署阻断 + 限流真实来源 + 测试契约）

**P0 · 部署阻断**

- **`app/core/rate_limit.py` 等 5 个文件此前未纳入版本控制**。`auth.py` / `avatar.py` 都 `import`
  这个模块，若按 Git 拉代码构建，容器启动即 `ModuleNotFoundError`、整站 502。
  已 `git add`：`rate_limit.py`、两个新测试、`.github/workflows/ci.yml`、`.gitattributes`
- 连带修复：CI 之前根本不在仓库里（`.github/` 未跟踪），「已有 CI」实际不生效

**安全 · 限流与密钥**

- **访客聊天限流的来源识别修正**：生产是 Caddy 反代到 `127.0.0.1:8000`，
  `websocket.client.host` 恒为反代地址，按它计数等于「全站每分钟 20 条」，两个访客互相锁死。
  改为优先取 `X-Forwarded-For` 的**最后一跳**（客户端可伪造前缀，反代追加的那段才可信），
  退路为 `X-Real-IP` → 连接地址；容器启动加 `--proxy-headers`，访问日志也能看到真实 IP
- **弱 `SECRET_KEY` 校验与 `DEBUG` 解耦**：原来只有 `DEBUG=false` 才拦，而演示环境
  （含 `docker-compose.prod.yml`）为了保住万能码登录把 `DEBUG` 设成了 `true`，
  于是 `.env.production` 里原样留着 `请替换为随机字符串` 也能启动，JWT 密钥可被猜中。
  现在弱密钥一律拒绝启动，只认显式的 `ALLOW_WEAK_SECRET=true`（本地 `backend/.env` 已开，生产不设）
- `/auth/send-code` 在无 Redis 时的 503 文案改为说明真实原因与出路
  （演示环境没有缓存服务，验证码存不下来）

**正确性**

- `guide_idea_stream` 不再吞掉 LLM 异常：原先失败时只 `warning` 后静默结束，前端显示
  「暂无建议，换个方向试试」——用户以为模型没想法，实际是调用失败且额度已消耗。改为上抛，由接口发 `error` 帧
- `/brainstorm/suggest/stream` 显式拒绝 `mode=generate`（400），不再静默当成 `hint`
- `_parse_extraction_response` 解析失败时返回与成功同构的字段集：原先少 `nodes`/`subject` 两个 key，
  模型偶发返回非 JSON 就会在下游 `result["nodes"]` 抛 `KeyError`，把可降级场景变成 500

**测试**

- 清空全部 5 个 `xfail`（此前把真实回归标成「预期失败」，永远不会变红）：
  fork 的 `nodes_count` 现为 3（2 知识点 + 书籍根）、`note.nodes_count` 同理、
  抽取提示词断言对齐 `categories` 树状格式、宠物成长改用 `growth_from_nodes()` 的凹曲线
- 新增 2 个用例：`mode=generate` 必须 400、`_client_ip` 取 XFF 最后一跳

**清理**

- 清理前端死代码：`AIAssistPanel` 的 `regenerate` 事件（从未 emit、父组件也不监听）、
  `hintResult` prop / ref（对话式面板改用 `hintMessages` 后已无人读）
- 根目录 `nul`（103B，Windows 保留名误产物）仍在：普通权限删除会被系统拒绝，
  `.gitignore` 已覆盖、不会被提交，需要管理员权限或先释放占用它的进程才能清掉

### 2026-11-04 · 二轮体检修复（流式崩溃 + 安全加固）

**P0 · 功能阻断**

- **修复 `/api/v1/brainstorm/suggest/stream` 提示分支必崩**：`_to_node()` 返回的是 pydantic 模型，
  而 `_sse()` 直接 `json.dumps`，抛 `TypeError: Object of type BrainstormNode is not JSON serializable`。
  异常发生在 `StreamingResponse` 已发出 200 之后，客户端只收到半截流，界面显示「暂无建议」，
  模型算出的结果被静默丢弃（线上日志已累计 12 次）。改为 `default=` 兜底序列化 + 每个分支自兜异常并补 `done` 帧
- 同时关闭反向代理缓冲（`X-Accel-Buffering: no` + `Cache-Control: no-cache`），保证增量帧即时下发
- 新增 4 个流式用例（正常建议 / 增量文本 / 上游异常仍需 `done` 且不回传内部报错 / 节点不存在），
  修复前这类问题 CI 完全拦不住

**安全加固**

- SSE 错误帧不再回传 `str(exc)`，内部异常只进日志，前端只看到泛化文案
- 新增 `ENABLE_API_DOCS`（默认 `false`）：演示环境常常 `DEBUG=true`，此前 `/docs`、`/openapi.json`
  会把完整接口面公开到公网；本地需要时在 `.env` 显式打开
- 新增 `SecurityHeadersMiddleware`（纯 ASGI，避免影响 SSE 流式）：`X-Content-Type-Options`、
  `X-Frame-Options`、`Referrer-Policy`、`Permissions-Policy`、`Cross-Origin-Opener-Policy`，
  仅在 `X-Forwarded-Proto: https` 时追加 HSTS（明文下加 HSTS 会锁死本地访问）
- 访客聊天（公开 WebSocket `/avatar/chat/{id}`）新增用量闸门：按「分身 + 来源 IP」每分钟 20 条、
  单条 500 字上限，防止匿名刷爆模型额度
- `SECRET_KEY` 校验加强：原先只拦完全等于 `change-me-in-production`，`change-me-demo-only`
  这类变体全部静默通过；现在命中 `change-me/secret/demo/请替换` 或长度 < 16 位时生产直接拒绝启动，
  长度 < 32 位给出告警（不阻断，避免误伤已有部署）
- `rate_limit` 降级日志改为每分钟最多一条（生产无 Redis 时原先每条调用都刷 WARNING）

**前端与文档**

- `api/brainstorm.js`：改用统一实例的 `baseURL`（不再硬编码 `/api/v1`）、支持 `AbortSignal`、
  401 时清凭据并弹登录框（原先流式请求绕过了 axios 拦截器，登录过期毫无提示）
- 构思面板再次提问/离开页面时中止上一条 SSE 连接，避免后端白跑生成
- 恢复被误删的 `docs/images/*`（10 张）与 `docs/demo/demo-video.mp4`——README 仍在引用，
  之前首页图片与视频链接全挂
- 重新构建 `frontend/dist`（此前停留在旧产物，`BookDetail.vue` 等改动未生效）
- 新增 `.gitattributes` 统一换行，消除 Windows 上反复出现的 `LF will be replaced by CRLF` 提示
- 测试基线：**254 passed / 1 skipped / 5 xfailed**，ruff 与 eslint 全绿

### 2026-11-04 · 安全与工程化修复（P0 / P2 整改）

**P0 · 高危**

- **万能验证码收紧到白名单**（新增 `DEV_LOGIN_PHONE_ALLOWLIST`）：修复前只比对验证码、不校验手机号，
  任何人拿公开的万能码 + 对方手机号即可登录对方账号。现在只有白名单内号码可用万能码登录，
  名单外一律 401；白名单为空时该功能整体不生效（安全默认值）。`docker-compose.prod.yml` 已收紧为演示号
- **SPA 回退路径穿越修复**：路由参数 `{full_path:path}` 可传入 `../`（uvicorn 还会把 `%2F` 解码成 `/`），
  原实现 `os.path.join` + `isfile` 直接返回文件，`/..%2F..%2Fbackend%2F.env` 能读走 SECRET_KEY、
  LLM/OCR Key 与数据库口令。改为 `realpath` + `commonpath` 校验，越界一律回退 `index.html`
- 修正 `_resolve_spa_dir()` 目录层级多退一级的问题（本地直接跑后端时永远找不到 `frontend/dist`，
  只有容器内碰巧可用）
- 登录失败计数收敛到 `app/core/rate_limit.py`：Redis 不可用时自动降级为进程内计数，
  不再出现「缓存一挂、限流整体失效」

**P2 · 工程化**

- 新增 CI（`.github/workflows/ci.yml`）：后端 ruff + pytest、前端 eslint + build
- 清理 7 处静默吞异常（笔记文件解析、抽取书名回退、知识脉络/概念查询、社区通知、克隆节点回滚），
  统一改为 `logger.warning(..., exc_info=True)`，排障不再靠猜
- 依赖瘦身：`passlib[bcrypt]` → 直接依赖 `bcrypt`（代码本就直调 bcrypt，passlib 是多余一层）
- `.gitignore` 补 `*.db-wal`、`*.db-shm`、`_openapi.json`、`_oa_check.json`，并清理仓库根目录残留文件
- 生产编排把令牌有效期收紧到 1 天；README 明确「HTTP 直连时 token 明文，须配域名走 Caddy 自动 HTTPS」
- 测试补齐：万能码白名单用例、Redis 不可用仍需限流用例、路径穿越 5 个用例；顺带修掉 2 个历史失败用例
  （万能码用例依赖本地 `.env`、上传超限 400→413 未同步）。基线：245 passed / 5 xfailed，ruff 全绿

### 2026-11-04 · 移除 Render 部署方案

- 删除 `render.yaml` 与 `docs/部署-免费云Render.md`：线上环境已固定为自建服务器
  （`docker-compose.prod.yml` + `deploy/setup-server.sh`），不再维护第二条免费的 PaaS 部署路径
- `README.md` 部署章节只讲自建服务器方案，移除「免费云部署指南」入口
- 清理 `Dockerfile`、`backend/app/core/config.py`、`backend/app/main.py`、
  `frontend/src/components/LoginModal.vue` 中指向 Render 的注释，改为中性描述

### 2026-10-14 · 文档与脚本一致性修复

- 测试基线更新为 **243 个用例（238 通过 / 5 xfail）**（文档中此前的 177 / 172 为历史值）
- 演示账号统一为演示号（旧文档中出现的**历史账号**已不在演示库中，号码不再在文档中列举）
- `docs/12-目录架构.md` 已并入 `docs/04-项目结构与目录架构.md`，文档编号现为 `00`–`09`
- `README.md` 部署章节改为与 `docs/部署-免费云Render.md` 一致（Render 免费档、零外部数据库依赖，
  该方案已于 2026-11-04 移除），
  并补充当前线上使用的自建服务器方案（`docker-compose.prod.yml` + `deploy/setup-server.sh`）
- `scripts/run_backend.bat`、`scripts/ci.bat` 去掉作者机器专属绝对路径：按脚本位置定位项目、自动探测 Python，
  并自动创建 `logs/`；`ci.bat` 增加 ruff 缺失时的明确提示（ruff 仅在 `requirements-dev.txt` 中）
- `scripts/setup.bat` 的 Neo4j 提示改为推荐 Docker（`deps/` 未随仓库分发）
- `backend/.env.example` 补齐 `DEMO_BOOTSTRAP`、`GRAPH_BACKEND`、`FRONTEND_DIST`、`CORS_ORIGINS`、
  `ALLOWED_EXTENSIONS`、`IMAGE_EXTENSIONS`、`SMS_*`(4 项)、`TIMEZONE_OFFSET_HOURS`、`APP_VERSION`、
  `AVATAR_KEYWORD_THRESHOLD`
- `.env.production.example` 补齐 `GRAPH_BACKEND`、`FRONTEND_DIST`
- `docker-compose.yml` 改为 `DEBUG=true` 且新增 `ALLOW_DEV_LOGIN=true`（与本地开发文档一致）；
  两个数据库口令改为带默认值，`docker compose up -d neo4j` 可直接执行（此前因必填校验会报错）
- 文档中的 `D:\Python313\python.exe` 统一改为 `python` / `py`（并说明 Store 占位程序的处理方式）

### 文档

- 精简并合并重叠文档：`docs/` 文档数由 14 篇降至 10 篇（另 `README.md` 索引）
  - `00-作品说明` + `11-场景背景与核心亮点` → `00-作品说明与场景亮点.md`
  - `01-需求规格说明书` + `02-产品需求文档(PRD)` → `01-需求规格说明书.md`
  - `03-高层架构设计(HLD)` + `04-系统架构` → `02-高层架构与系统设计.md`
  - `06-项目结构` + `12-目录架构` → `04-项目结构与目录架构.md`
  - 保留文档重新连续编号：前端设计规范→`03`、对话交接→`05`、CONTRIBUTING→`06`、DEBUG→`07`、PROMPTS→`08`、路演文稿→`09`
- 同步更新根 `README.md`（结构树 + 相关文档索引）、`docs/README.md`（文档一览 + 推荐阅读路径）及各文档交叉引用
- 测试基线数字更新为 `223 passed / 5 xfailed`（共 228 用例）

## 0.1.0 - 2026-10-10

首个交付版本：打通「笔记 → 知识图谱 → AI 反思 → 数字分身」的完整知识闭环。

### 新增

#### M1 基础架构

- FastAPI + uvicorn 后端脚手架，异步 SQLAlchemy（开发 SQLite / 生产 PostgreSQL）
- 手机号 + 短信验证码登录，JWT 签发与校验（`/api/v1/auth`）
- 关系库默认 SQLite（无 PostgreSQL 时）；Neo4j 不可用时图谱接口降级返回空数据，Redis 不可用时 `/auth/send-code` 返回 503（`DEBUG=true` 下 `123456` 万能码可经 `/auth/login` 旁路）
- 应用入口 lifespan、`/health` 健康检查

#### M2 笔记与知识图谱

- 笔记上传（Markdown / PDF / DOCX / TXT / PNG / JPG），图片经多模态模型 OCR 识别为文本后入库
- LLM 自动知识抽取（知识点 + 关系），异步抽取任务 + 指数退避重试
- 知识图谱写入 Neo4j，组织为「书本 → 目录 → 知识点」三级树
- 图谱节点 / 边 CRUD、节点来源、学科统计 `subject-stats`
- 抽取失败 / 为空的笔记重新抽取（`re-extract`）

#### M3 AI 反思引擎

- 基于掌握度阈值 + 间隔重复策略的反思问题生成
- APScheduler 每日定时调度
- 三维度（概念 / 逻辑 / 举例）作答评分与掌握度回写
- 站内通知（列表 / 未读数 / 标记已读）

#### M4 数字分身

- 知识点向量化（bge-m3，1024 维）写入 Neo4j 原生向量索引
- RAG 相似度检索（默认阈值 0.7，可配 `AVATAR_SIMILARITY_THRESHOLD`）+ 关键词兜底，防幻觉拒答
- 分身发布 / 配置 / 下线 / 统计
- WebSocket 流式对话（`welcome → sources → chunk → done`），前端打字机效果

#### M5 前端

- Vue 3 + Vite + Pinia + Vue Router + Element Plus + ECharts，共 11 个页面
- 知识花园 Dashboard（认知之树 + 宠物家园 + 成就星图）
- 知识图谱 GraphViewer（知识书架：3D 拟物化书本）；知识书详情 BookDetail（目录树 + 内容 + AI 摘要）
- 反思中心、数字分身配置、访客对话、知识广场（列表 / 详情 / 搜索）
- 全局悬浮宠物 PetFloat + 流式对话弹窗

#### M6 优化与上线

- Linear Aesthetic 深色科技风视觉重构（近黑基底 / 毛玻璃 / 青紫辉光）
- 知识广场社区模块（发布 / 列表 / 点赞 / 克隆 / 评论）
- 游戏化：注册即得独特宠物，知识输入驱动果实成长与收割
- 性能瘦身：Element Plus + ECharts 按需引入，主包约 1296 kB → 497 kB；图片自动转 WebP
- 可观测性：统一日志、TraceID、全局异常响应 `{code, message, detail, trace_id}`
- LLM Provider 抽象层与工厂降级（`services/providers/`）
- 测试基线：pytest 172 通过（共 177）/ 5 xfail，含 WebSocket 流式对话测试
- `scripts/ci.bat` 本地一键 CI（后端 pytest + 前端 build）
- 移动端响应式与可访问性（图标按钮 `aria-label`）

### 工程与文档

- 文档一致性修复：统一测试数字为 177（172 通过 / 5 xfail）、修正 `api/deps/` 路径、补录 `OCR_*` 配置与 `docs/12-目录架构.md`、统一文档日期戳
- 文档二次核对（以代码为准）：修正 User 模型字段、向量存储（Neo4j 向量索引）、Redis/Neo4j 降级口径、前端依赖与路由、接口清单（补全 graph/community/avatar/notes 端点）、宠物为 SSE、RAG 阈值默认 0.7、Node 版本等；删除与 `docs/12-目录架构.md` 重复的根目录 `架构.txt`
- 全部项目文档集中 `docs/`，按 `00`→`12` 数字前缀排序
- 新增 CONTRIBUTING、DEBUG、PROMPTS、场景背景与核心亮点等文档
- 开源交付配套：`LICENSE`（MIT）、`CHANGELOG.md`、`.editorconfig`
