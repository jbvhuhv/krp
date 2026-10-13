# 免费云部署指南（Render + Neo4j Aura Free）

> 目标：**零成本**得到一个长期可访问的体验地址，供评委/他人直接点开使用。
> 全程不需要信用卡（Render 免费档 + Neo4j Aura 免费版），也不需要备案。

---

## 一、部署后的效果

| 项目 | 说明 |
|---|---|
| 访问地址 | `https://<你的服务名>.onrender.com`（固定，自动 https） |
| 前端 | 由后端直接托管（单服务，同源，无跨域问题） |
| 数据 | 容器内 SQLite；**首次启动自动灌入演示数据**（32 篇笔记 / 12 个社区帖 / 反思记录等） |
| 知识图谱 | 接入 Neo4j Aura 免费版后，**719 个知识点 / 607 条关系**自动导入 |
| 演示账号 | 手机号 **13900000001**，验证码 **123456**（登录框里有提示） |
| 成本 | **￥0** |

---

## 二、三个免费组件

```
┌─────────────────────────────┐       ┌──────────────────────────┐
│ Render 免费 Web Service     │       │ Neo4j Aura Free          │
│  · FastAPI 后端             │──────▶│  · 知识图谱存储          │
│  · 前端构建产物（同源托管） │       │  · 719 节点 / 607 关系   │
│  · SQLite（启动自动灌数据） │       │  · 空库时自动导入        │
└─────────────────────────────┘       └──────────────────────────┘
                 ▲
                 │ 每 5 分钟 ping（防冷启动）
        ┌──────────────────┐
        │ UptimeRobot 免费 │
        └──────────────────┘
```

---

## 三、操作步骤

### 第 1 步：创建 Neo4j Aura 免费实例（约 3 分钟）

1. 打开 <https://console.neo4j.io/> → 用邮箱注册（免费，无需信用卡）
2. 选择 **AuraDB Free** → Create
3. 创建后**立即保存**弹出的连接信息（密码只显示一次）：
   - `NEO4J_URI`：形如 `neo4j+s://xxxxxxxx.databases.neo4j.io`
   - `NEO4J_USER`：`neo4j`
   - `NEO4J_PASSWORD`：创建时给的随机密码
4. 实例创建后需要 1–2 分钟才可用

> 免费版限制：实例闲置约 3 天后会**自动暂停**（数据保留，可手动恢复）。
> 配合第 3 步的保活监控（会访问图谱接口）可基本避免。

### 第 2 步：在 Render 部署（约 5 分钟）

1. 打开 <https://dashboard.render.com/> → 用 GitHub/邮箱注册（免费）
2. **New** → **Web Service**
3. 选择 **Public Git repository**（重要：Render 不支持 GitCode 账号授权，但支持公开仓库地址）
   - 填入：`https://gitcode.com/jbvhuhv/knowledge-reflection-platform.git`
   - Branch：`main`
4. **Runtime** 选择 **Docker**（仓库根目录已有 `Dockerfile`；Render 会自动识别）
5. **Instance Type** 选择 **Free**
6. **Region** 选 **Singapore**（离国内最近；若不可用选 Frankfurt）
7. 展开 **Environment Variables**，逐条添加：

| Key | Value |
|---|---|
| `DEBUG` | `true` |
| `ALLOW_DEV_LOGIN` | `true` |
| `DEMO_BOOTSTRAP` | `true` |
| `POSTGRES_URL` | `sqlite+aiosqlite:///./krp.db` |
| `SECRET_KEY` | 点 **Generate** 生成随机值（**不要手填默认值**） |
| `SCHEDULER_ENABLED` | `false` |
| `NEO4J_URI` | 第 1 步拿到的 `neo4j+s://...` |
| `NEO4J_USER` | `neo4j` |
| `NEO4J_PASSWORD` | 第 1 步保存的密码 |

8. 点 **Create Web Service** → 等待构建（首次约 5–10 分钟）
9. 构建完成后访问 `https://<服务名>.onrender.com` → 应能看到登录页

> 若不想手填环境变量，也可以把本仓库镜像到 GitHub 后用 `render.yaml`
> （Blueprint 一键部署，`NEO4J_*` 会以弹窗形式让你填写）。

### 第 3 步：配置保活，避免免费实例休眠（约 2 分钟）

Render 免费实例**闲置 15 分钟会休眠**，下一次访问需要 30–60 秒冷启动。
用免费的 UptimeRobot 每 5 分钟 ping 一次即可保持唤醒：

1. 打开 <https://uptimerobot.com/> → 注册（免费）
2. **Add New Monitor** → 类型 `HTTP(s)` → URL 填
   `https://<服务名>.onrender.com/health?deep=1`
   （`deep=1` 会顺带探测关系库与 Neo4j，**同时避免 Neo4j Aura 免费实例因闲置约 3 天被自动暂停**）
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
同时到 Neo4j Aura 删除免费实例，即彻底释放。

---

## 六、常见问题

| 现象 | 原因与处理 |
|---|---|
| 首次打开很慢（30–60 秒） | 免费实例冷启动，配置 UptimeRobot 保活即可 |
| 页面能开但"知识图谱"为空 | `NEO4J_*` 没配或 Aura 实例被暂停 → 检查变量、到 Aura 控制点恢复实例 |
| 登录后书架是空的 | 用**演示账号 13900000001** 登录（新手机号会自动建号，自然没有数据） |
| 构建失败、提示内存不足 | 免费构建内存有限；可本地 `npm run build` 后提交 `frontend/dist` 并改用 Python 运行时 |
| 上传笔记提示 AI 抽取失败 | 未配置 LLM Key（见上方"注意事项 1"），属预期行为 |
