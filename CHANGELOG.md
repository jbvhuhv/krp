# Changelog

本项目所有值得记录的变更都会记录在此文件。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## Unreleased

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
