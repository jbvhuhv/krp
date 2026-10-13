# 免费云部署指南（Render 免费档，零外部依赖）

> 目标：**零成本**得到一个长期可访问的体验地址，供评委/他人直接点开使用。
> 全程不需要信用卡、不需要备案，**也不需要任何外部数据库服务**。

---

## 一、部署后的效果

| 项目 | 说明 |
|---|---|
| 访问地址 | `https://<你的服务名>.onrender.com`（固定，自动 https） |
| 前端 | 由后端直接托管（单服务，同源，无跨域问题） |
| 数据 | 容器内 SQLite；**首次启动自动灌入演示数据**（32 篇笔记 / 12 个社区帖 / 反思记录等） |
| 知识图谱 | **内置演示图谱**：719 个知识点 / 607 条关系，启动即可用 |
| 演示账号 | 手机号 **13900000001**，验证码 **123456**（登录框里有提示） |
| 成本 | **￥0** |

---

## 二、架构：**不需要任何外部数据库**

```
┌──────────────────────────────────────────────┐
│ Render 免费 Web Service（单容器）            │
│  · FastAPI 后端                              │
│  · 前端构建产物（同源托管，无跨域）          │
│  · SQLite：笔记/广场/反思/数字分身           │
│  · 内置只读图谱：719 知识点 / 607 关系       │
│    （Neo4j 不可用时自动接管，无需外部服务）  │
└──────────────────────────────────────────────┘
                 ▲
                 │ 每 5 分钟 ping（防冷启动）
        ┌──────────────────┐
        │ UptimeRobot 免费 │
        └──────────────────┘
```

**为什么不用外部图数据库**：Neo4j Aura 免费版**不对中国大陆开放**
（创建实例会提示 `This service is not available in your region`）。
为此项目内置了一份只读演示图谱：

- Neo4j 可用 → 走 Neo4j（完整读写能力）
- Neo4j 不可用 → **自动切换内置只读图谱**（书架、知识树、知识画像全部有内容）
- 内置图谱**只对演示账号生效**，其他用户看到的是空图谱，不会误把演示数据当成自己的数据
- 写操作（新增/改名/删除知识点）在演示模式下会返回明确提示

> 如后续需要完整图谱能力（可编辑、向量检索），可在**国内云厂商**自建 Neo4j
> 或使用支持大陆地区的托管服务，再把 `NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD` 填进 Render 即可。

---

## 三、操作步骤（总共约 10 分钟，不需要外部数据库）

### 第 1 步：在 Render 部署（约 5 分钟）

1. 打开 <https://dashboard.render.com/> → 用 GitHub/邮箱注册（免费）
2. **New** → **Web Service**
3. 选择 **Public Git repository**（重要：Render 不支持 GitCode 账号授权，但支持公开仓库地址）
   - 填入：`https://gitcode.com/jbvhuhv/knowledge-reflection-platform.git`
   - Branch：`main`
4. **Runtime** 选择 **Docker**（仓库根目录已有 `Dockerfile`；Render 会自动识别）
5. **Instance Type** 选择 **Free**
6. **Region** 选 **Singapore**（离国内最近；若不可用选 Frankfurt）
7. 展开 **Environment Variables**，逐条添加（**只有这 6 条，没有数据库要配**）：

| Key | Value |
|---|---|
| `DEBUG` | `true` |
| `ALLOW_DEV_LOGIN` | `true` |
| `DEMO_BOOTSTRAP` | `true` |
| `POSTGRES_URL` | `sqlite+aiosqlite:///./krp.db` |
| `SECRET_KEY` | 点 **Generate** 生成随机值（**不要手填默认值**） |
| `SCHEDULER_ENABLED` | `false` |

> 可选：想启用图谱完整读写能力时，再加 `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`
> 与 `GRAPH_BACKEND=auto`（不配则自动使用内置只读演示图谱，知识图谱页照样有内容）。

8. 点 **Create Web Service** → 等待构建（首次约 5–10 分钟）
9. 构建完成后访问 `https://<服务名>.onrender.com` → 应能看到登录页

> 若不想手填环境变量，也可以把本仓库镜像到 GitHub 后用 `render.yaml`（Blueprint 一键部署）。

### 第 2 步：配置保活，避免免费实例休眠（约 2 分钟）

Render 免费实例**闲置 15 分钟会休眠**，下一次访问需要 30–60 秒冷启动。
用免费的 UptimeRobot 每 5 分钟 ping 一次即可保持唤醒：

1. 打开 <https://uptimerobot.com/> → 注册（免费）
2. **Add New Monitor** → 类型 `HTTP(s)` → URL 填
   `https://<服务名>.onrender.com/health?deep=1`
   （`deep=1` 会顺带探测关系库与图谱后端，确认演示环境各部分健康）
3. 监控间隔选 **5 minutes** → 保存

> 免费档每月有 750 实例小时，单个服务 24/7 运行约需 744 小时，刚好够用。

---

## 四、自检清单（部署完照着点一遍）

- [ ] 打开根地址 → 出现登录页、页面样式正常
- [ ] 点「登录」→ 登录框里能看到**演示环境提示**（手机号 13900000001 / 验证码 123456）
- [ ] 用演示账号登录 → 「我的笔记」有 32 篇、「知识广场」有 12 个作品
- [ ] 打开「知识图谱」→ 书架有知识书，点开能看到知识树
- [ ] 打开「反思中心」「数字分身」→ 有历史数据
- [ ] 用**手机浏览器**打开一次（评委常用手机点）

---

## 五、注意事项（务必了解）

### 1. 为什么不配 LLM/OCR 时"上传笔记"不能用
演示数据是**预先抽取好**的，所以浏览、图谱、反思等功能全部可用。
但**新上传笔记并自动抽取**需要调用大模型：

```ini
LLM_PROVIDER=maas
LLM_API_KEY=...        # 文本抽取必需
LLM_BASE_URL=...
LLM_MODEL=...

OCR_BASE_URL=...       # 图片笔记必需
OCR_API_KEY=...
OCR_MODEL=...
```

**建议**：评委体验以"浏览 + 查看图谱"为主，不配 Key 即可（**零泄露风险**）。
若确实要让体验者亲手上传，请使用**演示专用、低额度**的 Key，并定期轮换。

### 2. 免费实例的磁盘是临时的
容器重启后 SQLite 会回到镜像内初始状态 —— 但**启动引导会自动重新灌入演示数据**，
所以不会出现"打开是空的"。用户上传的内容不保证长期保留（演示用途足够）。

### 3. 安全提醒
- `ALLOW_DEV_LOGIN=true` 是**演示开关**，任何人用 `123456` 都能登录 → 不要把真实隐私数据放进来
- `SECRET_KEY` 必须用随机值（Render 的 Generate 按钮），不要沿用默认值
- 公开的演示地址**不要**配置真实业务用的 API Key

### 4. 更新代码后如何生效
Render 默认开启 `autoDeploy`：推送到 `main` 分支会自动重新构建部署。
也可以在 Render 控制点点 **Manual Deploy → Clear build cache & deploy**。

### 5. 关掉演示环境
在 Render 控制点 **Suspend**（暂停，免费且保留配置），或删除服务；
若有配置外部 Neo4j，也一并停用即可彻底释放。

---

## 七、附录：Render 控制台逐步指引

> 按顺序照做即可；每一步若界面与描述不符，截图留档，通常是 Render 改版。

| 步骤 | 操作 | 预期界面 |
|---|---|---|
| 1 | 打开 <https://dashboard.render.com/> → **Get Started** → 邮箱注册并验证 | 进入 Dashboard |
| 2 | 右上角 **New +** → 选 **Web Service** | 进入 "Git Repository" 选择页 |
| 3 | 页面**下半部分**找到 **Public Git repository** 输入框（不要在上面点 GitHub 授权） | 一个可直接填 URL 的输入框 |
| 4 | 填入 `https://gitcode.com/jbvhuhv/knowledge-reflection-platform.git` → **Continue** | 进入服务配置页 |
| 5 | **Name** 填 `krp-demo`；**Region** 选 `Singapore`；**Branch** 填 `main` | — |
| 6 | **Language/Runtime** 应为 **Docker**（仓库根有 Dockerfile，通常自动识别） | 若显示别的语言，手动改成 Docker |
| 7 | **Instance Type** 选 **Free** | 显示 $0/month |
| 8 | 展开 **Environment Variables** → 逐条 **Add Environment Variable**（6 条，见第三节表格） | `SECRET_KEY` 点 **Generate** 按钮生成 |
| 9 | 点 **Deploy Web Service** → 自动进入 **Logs** | 构建中 |
| 10 | 等待 5–10 分钟，日志出现 `Your service is live` | 页面顶部出现访问地址 |
| 11 | 复制地址（形如 `https://krp-demo-xxxx.onrender.com`）→ 浏览器打开 | 应看到登录页 |

**常见卡点**

| 情况 | 处理 |
|---|---|
| 找不到 "Public Git repository" | 它在授权列表**下方**；或把仓库镜像到 GitHub 后用 GitHub 授权 |
| 注册时要求填信用卡 | Render 免费档通常不需要；若被要求，先停下，避免误开付费 |
| 构建失败 | 把 Logs 最后 30 行发出来（多为依赖或内存问题） |
| 打开很慢（30–60 秒） | 免费实例冷启动；配置第 2 步的保活即可 |
| 图谱页为空 | 确认 `GRAPH_BACKEND=auto`；若自行填过 `NEO4J_*` 但地址不通，清空这三个变量 |

**部署后的自检**：用演示账号 **13900000001 / 123456** 登录，应看到「我的笔记 32 篇」「知识图谱 31 本书」「知识广场 12 个图谱」。

---

## 八、常见问题

| 现象 | 原因与处理 |
|---|---|
| 首次打开很慢（30–60 秒） | 免费实例冷启动，配置 UptimeRobot 保活即可 |
| 页面能开但"知识图谱"为空 | 确认 `GRAPH_BACKEND=auto`（默认）且镜像内含 `backend/demo/neo4j-demo.jsonl`；若自己配了 `NEO4J_*` 但地址不通，请清空这三个变量以启用内置图谱 |
| 登录后书架是空的 | 用**演示账号 13900000001** 登录（新手机号会自动建号，自然没有数据） |
| 构建失败、提示内存不足 | 免费构建内存有限；可本地 `npm run build` 后提交 `frontend/dist` 并改用 Python 运行时 |
| 上传笔记提示 AI 抽取失败 | 未配置 LLM Key（见上方"注意事项 1"），属预期行为 |
