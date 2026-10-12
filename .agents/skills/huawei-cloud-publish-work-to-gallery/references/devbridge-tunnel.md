# DevBridge 隧道运行要点（Linux 走内置 skill）

## 平台分工

| 平台 | 隧道 |
|------|------|
| **Linux（目标环境）** | 加载内置 skill **`huawei-cloud-jobenv-devbridge-tunnel`**，按其说明完成开隧道并取得 `envUrl`；不臆造/不自行拼 devbridge 命令 |
| **Windows** | **不使用 DevBridge**（无内置隧道能力），直接 `envUrl=""` |

> 2026-09-20 起：本发布 skill 不再内置 devbridge 下载/登录/spawn 脚本。隧道逻辑完全由目标环境的内置 skill `huawei-cloud-jobenv-devbridge-tunnel` 承载，仓库内只声明委托与降级出口，避免与内置 skill 双源漂移。

## Linux：开隧道（委托内置 skill）

1. **加载内置 skill** `huawei-cloud-jobenv-devbridge-tunnel`，按其操作说明执行（典型流程：创建隧道 → 配置端口 → 启动 host → 从日志解析公网 URL）。
2. 取到 `envUrl`（形如 `https://<tunnelId>-<port>.<region>-bridge.myhuaweicloud.com`）后继续 Step 3。
3. **降级出口**：内置 skill 不可用 / 隧道失败 / 无公网访问地址 → **`envUrl=""` 照常发布**（作品仍可提交，仅无在线访问地址）。

## 清理

发布流程结束（或无需隧道）时，按内置 skill 说明停 host 进程并删除隧道；不残留常驻隧道进程。

## 注意

- 隧道为联调/演示用途，非生产对外服务；公开分享内容才开匿名访问，含敏感数据的服务勿开。
- `envUrl` 为**可选**字段（平台接受空串占位），隧道开不起绝不阻塞发布。