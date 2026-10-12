# 大学生知识管理与反思平台

> 将碎片笔记转化为结构化知识图谱，通过 AI 主动提问引导反思，并将个人知识体系发布为可对话的 AI 数字分身。

## 参赛信息

| 项目 | 内容 |
|------|------|
| 作品名称 | 大学生知识管理与反思平台（宝藏库 KRP，Knowledge Reflection Platform） |
| 参赛学生 | 何春 |
| 队伍名称 | 创与闯 |
| 版本号 | v0.1.0 |
| 联系方式 | 19840470251 |
| 开发工具 | 华为云码道（CodeArts Doer） |

### 相关链接

| 链接 | 地址 |
|------|------|
| 代码仓库 | https://gitcode.com/jbvhuhv/knowledge-reflection-platform |
| 作品展览馆发布链接 | `https://gallery.developer.huaweicloud.com/gallery/____________________` ← **待填写：在华为云开发者作品展览馆发布后替换** |

> 提交提示：初赛期间每支队伍可多次迭代优化，最终成绩取截止前**历史最高提交版本**；提交完成后可在平台查看提交状态与初步审核结果。因此建议每次迭代后都重新提交一次。

## 项目简介

本平台面向大学生，提供"笔记 → 知识图谱 → AI 反思 → 数字分身"的知识闭环管理能力：

1. **笔记上传与知识图谱生成** — 上传 Markdown/PDF/Word/TXT/图片笔记，AI 自动抽取知识点与关系，生成可视化知识图谱（图片经多模态模型 OCR 识别后汇入同一抽取链路）
2. **AI 定时主动提问反思** — 基于知识图谱与间隔重复策略，定时生成反思问题，评估掌握度
3. **AI 数字分身发布** — 将个人知识图谱发布为可对话的 AI 角色，访客可基于其知识库提问

## 界面展示

> 以下均为本地实际运行界面的真实截图（无设计稿、无合成图）。

**知识广场：公开知识图谱社区，未登录即可浏览、搜索与克隆**

![知识广场：公开知识图谱社区，未登录即可浏览、搜索与克隆](docs/images/01-community.jpg)

**我的笔记：支持 Markdown / Word / PDF / TXT / 图片，AI 自动抽取知识点与关系**

![我的笔记：支持 Markdown / Word / PDF / TXT / 图片，AI 自动抽取知识点与关系](docs/images/02-notes.jpg)

**知识图谱：书本 → 目录 → 知识点三级结构，目录树与思维导图双栏联动**

![知识图谱（base64 内联测试）](data:image/jpeg;base64,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)

**图谱详情：节点以颜色区分分支、以光环与尺寸编码掌握度**

![图谱详情：节点以颜色区分分支、以光环与尺寸编码掌握度](docs/images/04-graph-detail.jpg)

**反思中心：依据知识点与复习间隔自动生成思辨性问题**

![反思中心：依据知识点与复习间隔自动生成思辨性问题](docs/images/05-reflection.jpg)

**作答与评分：支持文字/语音作答，AI 从概念准确性、逻辑完整性、举例合理性三维评分**

![作答与评分：支持文字/语音作答，AI 从概念准确性、逻辑完整性、举例合理性三维评分](docs/images/06-reflection-answer.jpg)

**知识花园：认知之树随知识输入生长，宠物养成、连续打卡与六维雷达画像**

![知识花园：认知之树随知识输入生长，宠物养成、连续打卡与六维雷达画像](docs/images/07-garden.jpg)

**数字分身：把个人知识库发布为可对外对话的 AI 角色**

![数字分身：把个人知识库发布为可对外对话的 AI 角色](docs/images/08-avatar.jpg)

**分身对话：访客免登录提问，回答附引用来源，超出知识范围会明确拒答**

![分身对话：访客免登录提问，回答附引用来源，超出知识范围会明确拒答](docs/images/09-avatar-chat.jpg)

**通知中心：点赞、评论、克隆实时通知作者**

![通知中心：点赞、评论、克隆实时通知作者](docs/images/10-notification.jpg)

## 演示视频

**功能演示视频（2 分 47 秒，中文配音解说）**：[`docs/demo/demo-video.mp4`](docs/demo/demo-video.mp4)

内容：未登录浏览广场 → 手机号验证码登录 → 笔记上传与 AI 抽取 → 翻开知识书查看图谱 → 反思作答与三维评分 → 知识花园与六维画像 → 数字分身访客对话（附引用来源）→ 通知中心。

> 解说词全文（含逐段时轴）：见参赛材料《功能演示视频-解说词.docx》。
## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue3 + Vite + Pinia + Element Plus + ECharts + Axios | 组合式 API，图谱可视化，WebSocket 流式对话，深蓝科技风毛玻璃 UI |
| 后端 | FastAPI + uvicorn | 异步高性能，自动 OpenAPI 文档 |
| 图数据库 | Neo4j 5.x | 知识图谱存储与关系查询（不可用时优雅降级） |
| 关系数据库 | SQLite（开发）/ PostgreSQL 16（生产） | 用户、笔记、反思记录、社区帖子等结构化数据 |
| 缓存 | Redis 7 | 验证码限流等缓存（可选；未配置时 `/auth/send-code` 返回 503，`DEBUG=true` 时可用万能码 `123456` 于 `/auth/login` 旁路登录） |
| 异步任务 | FastAPI BackgroundTasks | 知识抽取等后台任务（进程内执行，非独立队列） |
| AI 服务 | MaaS（华为云模型即服务） | LLM 知识抽取、问题生成、分身对话、Embedding |
| 图片识别 | 多模态视觉模型（OpenAI 兼容，OCR_* 配置） | 图片笔记识别为文本后汇入知识抽取链路 |
| 向量存储 | Neo4j 5.x 原生向量索引 | 知识点 Embedding 与相似度检索（RAG） |
| 容器化 | Docker Compose（可选 / 生产参考） | 本地开发无需 Docker：默认 SQLite + 本地 Neo4j |

## 项目结构

```
demo1/
├── README.md                              # 本文件
├── LICENSE                                # MIT License（版权人：KRP Team）
├── CHANGELOG.md                           # 版本变更记录
├── .editorconfig                          # 编辑器编码/换行/缩进统一规范
├── .gitignore                             # 忽略 .env/*.db/*.log/uploads/dist 等
├── docker-compose.yml                     # 容器编排（可选/生产参考）：Neo4j + PostgreSQL + Redis + Backend
├── scripts/                               # 本地脚本（setup.bat / run_backend.bat / ci.bat）
├── deps/                                  # 第三方运行时依赖（JDK / Maven / Neo4j，本地，已排除版本控制）
├── logs/                                  # 运行时日志（后端 / 前端输出）
├── docs/                                  # 全部项目文档（按阅读顺序编号）
│   ├── 00-作品说明与场景亮点.md           # 场景背景/功能架构/核心亮点/环境依赖/码道应用
│   ├── 01-需求规格说明书.md               # 需求规格（21 个 User Story + 验收标准 + 交互原型 + 里程碑）
│   ├── 02-高层架构与系统设计.md           # 架构图/模块划分/技术选型/数据流/RAG 与调度算法/部署
│   ├── 03-前端设计规范.md                 # 前端设计规范（Token/布局/组件/页面）
│   ├── 04-项目结构与目录架构.md           # 目录组织/文件架构/模块职责/依赖方向
│   ├── 05-对话交接.md                     # 对话/开发交接记录
│   ├── 06-CONTRIBUTING.md                 # 贡献指南（环境准备/代码规范/提交规范）
│   ├── 07-DEBUG.md                        # 故障排查（Neo4j/MaaS/跨域/WS 与 SSE）
│   ├── 08-PROMPTS.md                      # Prompt 集中治理说明
│   └── 09-路演文稿.md                     # 项目推介 / 融资路演文稿
├── backend/                               # FastAPI 后端
│   ├── app/
│   │   ├── main.py                        # 应用入口 + lifespan + /health
│   │   ├── scheduler.py                   # APScheduler 每日反思定时任务
│   │   ├── core/                          # 基础设施（config / database / security / logger / exceptions / middleware / prompt_manager / schema_migrations / constants）
│   │   ├── api/
│   │   │   ├── deps/                      # 依赖注入（按业务域拆分，__init__ 全量再导出）
│   │   │   │   ├── auth_deps.py           # 认证依赖（当前用户 / 可选用户）
│   │   │   │   ├── ai_deps.py             # AI 服务工厂
│   │   │   │   ├── graph_deps.py          # 图谱服务
│   │   │   │   ├── notes_deps.py          # 知识抽取服务
│   │   │   │   ├── reflection_deps.py     # 反思服务
│   │   │   │   ├── avatar_deps.py         # 数字分身服务
│   │   │   │   └── notification_deps.py   # 通知服务
│   │   │   └── v1/
│   │   │       ├── router.py              # 路由聚合（统一前缀 /api/v1）
│   │   │       └── endpoints/             # 8 个业务域端点
│   │   │           ├── auth.py            # 认证：发送验证码/登录/me
│   │   │           ├── notes.py           # 笔记：上传/列表/详情/删除
│   │   │           ├── graph.py           # 图谱：节点CRUD/边/来源/subject-stats
│   │   │           ├── reflection.py      # 反思：问题/作答/历史/调度
│   │   │           ├── avatar.py          # 分身：发布/配置/统计/对话WS
│   │   │           ├── community.py       # 社区：发布/列表/详情/点赞/克隆
│   │   │           ├── notifications.py   # 通知：列表/已读
│   │   │           └── pet.py             # 宠物：状态/音色/收割/投喂/流式对话
│   │   ├── models/                        # SQLAlchemy ORM（User, Note, Reflection*, Avatar, ChatMessage, Notification, CommunityPost, CommunityComment, CommunityLike, Pet）
│   │   ├── schemas/                       # Pydantic 请求/响应模型
│   │   └── services/                      # 业务逻辑
│   │       ├── providers/                 # LLM Provider 抽象层（base / maas / openai / vision + 工厂）
│   │       ├── ai/                        # AI 服务实现（base + 5 个场景 Mixin）
│   │       │   ├── base.py                # AIServiceBase + LLM/Embedding provider 工厂
│   │       │   ├── extraction_ai.py       # 知识抽取
│   │       │   ├── quiz_ai.py             # 反思出题
│   │       │   ├── scoring_ai.py          # 答案评分
│   │       │   ├── avatar_ai.py           # 分身对话
│   │       │   └── pet_ai.py              # 宠物流式对话
│   │       ├── ai_service.py              # 兼容 shim（转发 services/ai/）
│   │       ├── file_parser.py             # 文件解析（text/pdf/docx）
│   │       ├── ocr_service.py             # 图片笔记 OCR（多模态模型识别为文本）
│   │       ├── extraction_service.py      # 异步知识抽取（日志 + 重试）
│   │       ├── graph/                     # Neo4j 图谱实现
│   │       │   ├── constants.py           # 节点/关系标签常量
│   │       │   ├── crud.py                # 节点/边 CRUD
│   │       │   ├── tree.py                # 三级树构建
│   │       │   ├── vector.py              # 向量索引与检索
│   │       │   └── stats.py               # 学科统计
│   │       ├── graph_service.py           # 兼容 shim（转发 services/graph/）
│   │       ├── reflection_service.py      # 艾宾浩斯调度+问题生成+评分
│   │       ├── avatar_service.py          # 知识画像+发布+RAG防幻觉对话
│   │       ├── pet_service.py             # 宠物成长数学/情感状态机/对话记忆/主动关怀
│   │       └── notification_service.py    # 站内信创建/列表/已读
│   ├── tests/                             # pytest 测试（234 通过，5 个已知 xfail）
│   │   ├── conftest.py                    # 测试 fixtures
│   │   ├── test_auth.py                   # 认证测试
│   │   ├── test_notes_upload.py           # 上传测试（含图片 OCR/重新抽取）
│   │   ├── test_extraction.py             # 抽取测试（含重试）
│   │   ├── test_ocr_service.py            # 图片 OCR 服务测试
│   │   ├── test_graph.py                  # 图谱测试
│   │   ├── test_reflection.py             # 反思测试
│   │   ├── test_avatar.py                 # 分身测试
│   │   ├── test_avatar_ws.py              # 分身 WebSocket 流式对话测试
│   │   ├── test_community.py              # 社区测试（帖子/列表/详情/点赞/克隆）
│   │   ├── test_notifications.py          # 站内信测试
│   │   ├── test_pet.py                    # 宠物测试（身份/成长数学/收取溢出/情感/关怀）
│   │   └── test_scheduler.py              # 定时任务测试
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── pytest.ini
│   └── .env.example
└── frontend/                              # Vue3 前端
    ├── package.json                       # 依赖：vue, pinia, element-plus, echarts, axios
    ├── vite.config.js                     # Vite 配置 + API 代理 + vite-imagetools
    ├── index.html
    └── src/
        ├── main.js                        # 按需注册 Element Plus 组件/图标 + Pinia + Router（unplugin 自动引入）
        ├── App.vue                        # 根组件
        ├── api/
        │   ├── request.js                 # Axios 实例 + JWT 拦截器
        │   ├── index.js                   # 聚合导出（re-export 各业务域 API）
        │   ├── auth.js                    # 认证 API
        │   ├── notes.js                   # 笔记 API
        │   ├── graph.js                   # 图谱 API
        │   ├── reflection.js              # 反思 API
        │   ├── avatar.js                  # 数字分身 API
        │   ├── community.js               # 社区 API
        │   └── pet.js                     # 宠物 API
        ├── router/index.js                # 路由表（含兜底重定向；无路由守卫）
        ├── stores/                        # Pinia（user.js 登录态 / demo.js 演示模式）
        ├── layouts/MainLayout.vue         # 主布局（220px 深蓝侧边栏 + 毛玻璃顶栏）
        ├── components/                    # LoginModal / PetFloat / PetAvatar / HoloTrophyIcon
        ├── styles/main.css                # 全局深蓝科技风样式 + Element Plus 暗色覆盖
        ├── utils/                         # logger.js / format.js / petStage.js / echarts.js
        └── views/                         # 按业务域分子目录
            ├── dashboard/Dashboard.vue    # 知识花园（动态问候语+宠物家园：认知之树与宠物状态）
            ├── notes/                     # Notes.vue / NoteCategory.vue
            ├── graph/                     # GraphViewer.vue / BookDetail.vue / components/（3 个弹窗）
            ├── reflection/Reflection.vue  # 反思（单列卡片流+雷达图+语音+时间线）
            ├── avatar/                    # Avatar.vue / VisitorChat.vue
            └── community/                 # Community.vue / CommunityDetail.vue / SearchResults.vue
```

## 快速开始

### 1. 环境要求

- Python 3.12+
- Docker & Docker Compose（可选；本地开发无需 Docker，关系库默认 SQLite，Neo4j 可本地启动）
- Node.js 18+（前端）

### 2. 启动基础设施

本地开发**默认无需 Docker**：关系库自动使用 SQLite（`backend/krp.db`），仅需一个 Neo4j（可用下方 `deps/` 本地启动或 Docker）。若需完整容器化栈（Neo4j + PostgreSQL + Redis + Backend），可用 Docker Compose：

```bash
docker-compose up -d
```

启动后服务端口：

| 服务 | 端口 | 说明 |
|------|------|------|
| Backend (FastAPI) | 8000 | API 服务 |
| PostgreSQL | 5432 | 关系数据库 |
| Neo4j Browser | 7474 | 图数据库 Web 界面 |
| Neo4j Bolt | 7687 | 图数据库协议端口 |
| Redis | 6379 | 缓存 |

> **本地开发（无 Docker）：** 关系库使用 SQLite（无需启动）；Redis 可选，未配置时 `/auth/send-code` 返回 503（`DEBUG=true` 下 `123456` 万能码可经 `/auth/login` 旁路）。Neo4j 可用 Docker 单独启动或 `deps/` 本地启动：
>
> ```bash
> docker-compose up -d neo4j
> ```
>
> Bolt `7687` / HTTP `7474`（`NEO4J_URI=bolt://localhost:7687`，用户 `neo4j` / 密码 `krp123456`）。
>
> 提示：`deps/` 目录仅供本项目开发机使用（内含本地 JDK / Maven / Neo4j 构建产物），已从版本控制中排除，开源使用者无需关心。

### 3. 本地开发（后端）

```bash
cd backend
cp .env.example .env          # 编辑配置，填入 MAAS_API_KEY 等
D:\Python313\python.exe -m pip install -r requirements.txt
D:\Python313\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> Windows 本地开发请使用 `D:\Python313\python.exe`（`python` 可能是 Microsoft Store 占位程序）。

访问 `http://localhost:8000/docs` 查看 OpenAPI 交互文档。

### 4. 运行测试

```bash
cd backend
D:\Python313\python.exe -m pytest -v
```

或在项目根目录运行一键 CI（后端测试 + 前端构建）：

```bash
scripts\ci.bat
```

### 5. 本地开发（前端）

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`，Vite 代理 `/api` 到后端 `http://localhost:8000`。

访客对话页地址：`http://localhost:5173/chat/{avatarId}`（无需登录）。

## API 接口概览

### 已实现

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/send-code` | 发送短信验证码（限流：60s/次，5次/天） |
| POST | `/api/v1/auth/login` | 手机号+验证码登录（未注册自动创建），返回 JWT Token |
| GET | `/api/v1/auth/me` | 获取当前登录用户信息 |
| POST | `/api/v1/notes/upload` | 上传笔记（含图片，图片经多模态模型 OCR 识别），返回笔记 ID + 任务 ID，异步触发知识抽取 |
| GET | `/api/v1/notes` | 当前用户笔记列表 |
| GET | `/api/v1/notes/{noteId}` | 笔记详情 |
| DELETE | `/api/v1/notes/{noteId}` | 删除笔记 |
| POST | `/api/v1/notes/{noteId}/re-extract` | 对抽取失败/为空的笔记重新抽取（重置为 pending） |
| GET | `/api/v1/graph/books` | 获取知识书列表（书架视图数据源） |
| GET | `/api/v1/graph/tree/{bookId}` | 获取指定知识书的三级树（目录 + 知识点） |
| GET | `/api/v1/graph/{userId}` | 获取知识图谱（支持学科过滤） |
| GET | `/api/v1/graph/subject-stats` | 学科维度知识统计（知识画像雷达图数据源） |
| POST | `/api/v1/graph/nodes` | 手动创建知识节点（书本） |
| POST | `/api/v1/graph/categories` | 手动创建目录节点 |
| POST | `/api/v1/graph/knowledge` | 手动创建知识点节点 |
| PUT | `/api/v1/graph/nodes/{nodeId}` | 更新节点信息 |
| DELETE | `/api/v1/graph/nodes/{nodeId}` | 删除节点（及关联边） |
| POST | `/api/v1/graph/edges` | 创建节点间关系 |
| GET | `/api/v1/graph/nodes/{nodeId}/source` | 查看节点来源笔记 |
| POST | `/api/v1/graph/nodes/{nodeId}/ai-summary` | 为节点生成 AI 摘要 |
| GET | `/api/v1/reflection/today` | 获取今日反思问题（无则自动生成） |
| POST | `/api/v1/reflection/answer` | 提交作答并获取 AI 评估反馈 |
| GET | `/api/v1/reflection/history` | 查看反思历史记录（分页） |
| GET | `/api/v1/reflection/mastery` | 查看掌握度趋势 |
| GET | `/api/v1/reflection/schedule` | 获取反思调度设置 |
| PUT | `/api/v1/reflection/schedule` | 更新反思频率与时间段 |
| POST | `/api/v1/avatar/avatar-image` | 上传分身头像 |
| POST | `/api/v1/avatar/publish` | 发布数字分身，生成唯一分享链接 |
| POST | `/api/v1/avatar/unpublish` | 下线分身，停止可对话 |
| PUT | `/api/v1/avatar/config` | 配置对话风格/欢迎语/知识范围 |
| GET | `/api/v1/avatar/me` | 获取当前用户分身信息 |
| GET | `/api/v1/avatar/{avatarId}` | 访客获取已上线分身公开信息 |
| GET | `/api/v1/avatar/{avatarId}/stats` | 对话统计与高频提问 |
| GET | `/api/v1/avatar/{avatarId}/conversations` | 访客会话列表（会话聚合） |
| GET | `/api/v1/avatar/{avatarId}/conversations/{visitorId}` | 指定访客的对话明细 |
| WS | `/api/v1/avatar/chat/{avatarId}` | 访客与分身流式对话（含来源标注） |
| GET | `/api/v1/notifications` | 获取站内通知列表（含未读数） |
| PUT | `/api/v1/notifications/{notificationId}/read` | 标记通知已读 |
| GET | `/api/v1/community/posts` | 知识广场公开图谱列表（分页/标签过滤/排序，无需登录） |
| GET | `/api/v1/community/my-posts` | 当前用户发布的帖子列表 |
| GET | `/api/v1/community/posts/{postId}` | 图谱详情（浏览量+1，无需登录） |
| POST | `/api/v1/community/posts` | 发布个人图谱到广场（需登录） |
| POST | `/api/v1/community/posts/{postId}/visibility` | 切换帖子公开/撤回 |
| DELETE | `/api/v1/community/posts/{postId}` | 删除帖子 |
| GET | `/api/v1/community/posts/{postId}/comments` | 帖子评论列表 |
| POST | `/api/v1/community/posts/{postId}/comments` | 发表评论 |
| DELETE | `/api/v1/community/comments/{commentId}` | 删除评论 |
| POST | `/api/v1/community/cover` | 上传帖子封面 |
| POST | `/api/v1/community/posts/{postId}/like` | 点赞/取消点赞（需登录，幂等） |
| POST | `/api/v1/community/posts/{postId}/fork` | 一键克隆图谱到个人知识库（需登录，新节点 mastery=0） |
| GET | `/api/v1/pet/status` | 获取宠物与认知之树状态 |
| POST | `/api/v1/pet/voice` | 保存宠物音色预设（账号级） |
| POST | `/api/v1/pet/harvest` | 收获认知之树果实 |
| POST | `/api/v1/pet/feed` | 投喂宠物 |
| POST | `/api/v1/pet/chat` | 与宠物流式对话（SSE） |
| GET | `/health` | 健康检查 |

### 骨架待实现

无遗留骨架，后端全部实现。

## 配置说明

复制 `backend/.env.example` 为 `backend/.env`，关键配置项：

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `MAAS_API_KEY` | MaaS 大模型 API Key | （需填入） |
| `MAAS_BASE_URL` | MaaS 服务地址 | （需填入） |
| `MAAS_MODEL` | LLM 模型名称 | pangu |
| `MAAS_EMBEDDING_MODEL` | Embedding 模型名称 | bge-m3 |
| `OCR_API_KEY` | 图片识别多模态模型 API Key（不填则图片笔记不可用） | （可选） |
| `OCR_BASE_URL` | 图片识别服务地址（OpenAI 兼容） | （可选） |
| `OCR_MODEL` | 图片识别多模态模型名称 | （可选） |
| `EMBEDDING_DIMENSION` | 向量维度（需与模型一致） | 1024 |
| `AVATAR_SIMILARITY_THRESHOLD` | RAG 相似度阈值，低于则拒答 | 0.7 |
| `AVATAR_TOP_K` | RAG 检索返回条数 | 5 |
| `SHARE_BASE_URL` | 分身分享链接前端基址 | http://localhost:5173 |
| `UPLOAD_DIR` | 笔记文件存储目录 | ./uploads |
| `MAX_FILE_SIZE` | 最大文件大小（字节） | 10485760 (10MB) |
| `NEO4J_URI` | Neo4j 连接地址 | bolt://localhost:7687 |
| `SECRET_KEY` | JWT 签名密钥 | （生产环境必须修改） |

## 开发路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| M1 基础架构 | 脚手架 + 数据库 + 认证模块 | ✅ 完成 |
| M2 笔记与知识图谱 | 上传 + 知识抽取 + Neo4j 建图 + 图谱CRUD | ✅ 完成 |
| M3 AI 反思引擎 | 提问生成 + APScheduler 定时调度 + 掌握度评估 + 站内通知 | ✅ 完成 |
| M4 数字分身 | Neo4j向量索引 + RAG防幻觉 + 分身对话 | ✅ 完成 |
| M5 前端 | Vue3 全部页面 | ✅ 完成 |
| M6 优化与上线 | 深蓝科技风视觉重构 + 社区模块 + 性能/安全/测试/部署 | 🔄 进行中（视觉重构+社区+安全加固+性能瘦身+响应式+CI 已完成） |

## 相关文档

- [作品说明与场景亮点](docs/00-作品说明与场景亮点.md) — 场景背景、功能架构、核心亮点、环境依赖与码道应用
- [需求规格说明书](docs/01-需求规格说明书.md) — 21 个 User Story + 验收标准 + 交互原型 + 里程碑
- [高层架构与系统设计](docs/02-高层架构与系统设计.md) — 架构图、模块划分、技术选型、数据流、RAG/调度算法与部署
- [前端设计规范](docs/03-前端设计规范.md) — 设计 Token、全局布局、组件规范、页面设计
- [项目结构与目录架构](docs/04-项目结构与目录架构.md) — 目录组织、文件架构与模块职责
- [对话交接文档](docs/05-对话交接.md) — 当前进度与后续交接
- [贡献指南](docs/06-CONTRIBUTING.md) — 环境准备、代码规范、提交规范
- [调试排查](docs/07-DEBUG.md) — Neo4j / MaaS / 跨域 / WS 与 SSE 排查路径
- [Prompt 治理](docs/08-PROMPTS.md) — Prompt 集中管理与防注入约定
- [路演文稿](docs/09-路演文稿.md) — 项目推介 / 融资路演文稿