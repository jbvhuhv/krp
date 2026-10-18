#!/usr/bin/env bash
# =============================================================================
# 一键部署脚本：大学生知识管理与反思平台（自建服务器 / 香港 VPS）
#
# 适用：Ubuntu 22.04 / 24.04（2C2G 起），全新机器
# 幂等：可重复执行（已完成的步骤会跳过）
#
# 用法（在服务器上以 root 执行）：
#   bash setup-server.sh                         # 无域名，纯 IP 访问（HTTP）
#   DOMAIN=krp.example.com bash setup-server.sh  # 有域名，自动申请 HTTPS 证书
#
# 可选环境变量：
#   DOMAIN          域名（留空则用 IP + 80 端口）
#   LLM_API_KEY     文本抽取用的大模型 Key（留空则只能浏览演示数据，不能抽取新笔记）
#   OCR_API_KEY     图片笔记用的多模态 Key（留空则不支持图片笔记）
#   LLM_BASE_URL / LLM_MODEL / OCR_BASE_URL / OCR_MODEL  默认指向免费额度的千问 MaaS
#   REPO_URL        仓库地址（默认 GitCode）
# =============================================================================
set -euo pipefail

DOMAIN="${DOMAIN:-}"
LLM_API_KEY="${LLM_API_KEY:-}"
OCR_API_KEY="${OCR_API_KEY:-}"
LLM_BASE_URL="${LLM_BASE_URL:-https://maas.qianwenaiapi.com/compatible-mode}"
LLM_MODEL="${LLM_MODEL:-qwen3.5-omni-flash-2026-03-15}"
OCR_BASE_URL="${OCR_BASE_URL:-https://maas.qianwenaiapi.com/compatible-mode}"
OCR_MODEL="${OCR_MODEL:-qwen3.5-omni-flash-2026-03-15}"
REPO_URL="${REPO_URL:-https://gitcode.com/jbvhuhv/knowledge-reflection-platform.git}"
APP_DIR="${APP_DIR:-/opt/krp}"

log() { echo -e "\n\033[1;36m==> $*\033[0m"; }
ok()  { echo -e "    \033[1;32m✔ $*\033[0m"; }
warn(){ echo -e "    \033[1;33m! $*\033[0m"; }

[[ $EUID -eq 0 ]] || { echo "请用 root 运行（sudo -i 后重试）"; exit 1; }

# ---------------------------------------------------------------- 1. 系统准备
log "1/9 系统准备（时区、软件源、基础工具）"
export DEBIAN_FRONTEND=noninteractive
timedatectl set-timezone Asia/Shanghai || true
apt-get update -qq
apt-get install -y -qq curl git ca-certificates gnupg lsb-release ufw fail2ban jq >/dev/null
ok "基础工具就绪"

# 2G 内存的机器补 2G swap，避免 Neo4j 峰值 OOM
# 注意：mkswap 在部分 util-linux 版本不支持 -q，故不使用该参数；每步独立执行便于排错
if [[ ! -f /swapfile ]]; then
  log "1b 创建 2G swap（防 OOM）"
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
fi
swapon /swapfile 2>/dev/null || true
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
if swapon --show | grep -q '/swapfile'; then
  ok "swap 已启用：$(free -h | awk '/Swap/{print $2}')"
else
  warn "swap 未生效（不影响运行，但峰值内存风险略高）"
fi

# ---------------------------------------------------------------- 2. Docker
log "2/9 安装 Docker 与 compose 插件"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh >/dev/null
  systemctl enable --now docker >/dev/null
fi
docker compose version >/dev/null 2>&1 || apt-get install -y -qq docker-compose-plugin >/dev/null
ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) / $(docker compose version --short)"

# 国内/香港机器：配置镜像加速（可选，失败不阻断）
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat >/etc/docker/daemon.json <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
JSON
  systemctl restart docker
  ok "已限制容器日志大小（防磁盘被日志写满）"
fi

# ---------------------------------------------------------------- 3. 代码
log "3/9 拉取代码到 $APP_DIR"
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" pull --ff-only || warn "拉取失败（可能有本地改动），继续使用现有代码"
else
  mkdir -p "$(dirname "$APP_DIR")"
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
ok "代码版本：$(git rev-parse --short HEAD) $(git log -1 --pretty=%s | cut -c1-40)"

# ---------------------------------------------------------------- 4. 生产配置
log "4/9 生成生产配置 .env.production"
ENV_FILE="$APP_DIR/.env.production"
if [[ ! -f "$ENV_FILE" ]]; then
  SECRET_KEY="$(openssl rand -hex 32)"
  NEO4J_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-16)"
  cat >"$ENV_FILE" <<EOF
# 由 setup-server.sh 自动生成于 $(date '+%F %T')
SECRET_KEY=$SECRET_KEY
NEO4J_PASSWORD=$NEO4J_PASSWORD
POSTGRES_URL=sqlite+aiosqlite:////data/krp.db
# 生产默认关闭调试与万能验证码；需要演示时请临时改并用完即关
DEBUG=false
ALLOW_DEV_LOGIN=false
SMS_DEV_MASTER_CODE=
DEMO_BOOTSTRAP=true
LLM_PROVIDER=maas
LLM_API_KEY=$LLM_API_KEY
LLM_BASE_URL=$LLM_BASE_URL
LLM_MODEL=$LLM_MODEL
OCR_BASE_URL=$OCR_BASE_URL
OCR_API_KEY=$OCR_API_KEY
OCR_MODEL=$OCR_MODEL
EOF
  chmod 600 "$ENV_FILE"
  ok "已生成（SECRET_KEY 与 Neo4j 密码均为随机值，权限 600）"
else
  ok ".env.production 已存在，保留现有配置"
fi
if [[ -z "$LLM_API_KEY" ]]; then
  warn "未提供 LLM_API_KEY：评委可浏览演示数据，但「上传笔记→自动抽取」会失败"
fi

# 部署时用到的生产编排文件必须存在
[[ -f docker-compose.prod.yml ]] || { echo "缺少 docker-compose.prod.yml，请确认代码版本"; exit 1; }

# ---------------------------------------------------------------- 5. 启动
log "5/9 构建并启动容器（首次约 3–6 分钟）"
COMPOSE="docker compose -f docker-compose.prod.yml --env-file $ENV_FILE"
$COMPOSE up -d --build

log "5b 等待服务就绪"
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  sleep 5
done
curl -fsS http://127.0.0.1:8000/health && echo || { warn "健康检查未通过，查看日志：$COMPOSE logs --tail=80 app"; exit 1; }
ok "应用已监听 127.0.0.1:8000"

# ---------------------------------------------------------------- 6. 反向代理 + HTTPS
log "6/9 安装 Caddy 反向代理（有域名则自动申请 HTTPS）"
if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi
if [[ -n "$DOMAIN" ]]; then
  cat >/etc/caddy/Caddyfile <<EOF
$DOMAIN {
    encode gzip zstd
    # 限制请求体大小，避免超大上传把容器内存打满（应用侧上限 10MB）
    request_body {
        max_size 12MB
    }
    reverse_proxy 127.0.0.1:8000
}
EOF
  ok "Caddyfile 已配置域名 $DOMAIN（自动 HTTPS）"
else
  cat >/etc/caddy/Caddyfile <<'EOF'
:80 {
    encode gzip zstd
    # 限制请求体大小，避免超大上传把容器内存打满（应用侧上限 10MB）
    request_body {
        max_size 12MB
    }
    reverse_proxy 127.0.0.1:8000
}
EOF
  ok "Caddyfile 已配置为 IP + 80 端口访问（HTTP）"
  warn "想上 https：买域名后执行 DOMAIN=你的域名 bash $APP_DIR/deploy/renew-domain.sh"
fi
systemctl enable --now caddy >/dev/null
systemctl reload caddy || systemctl restart caddy
ok "Caddy 已启动"

# ---------------------------------------------------------------- 7. 防火墙
log "7/9 防火墙与防爆破"
ufw allow 22/tcp >/dev/null 2>&1 || true
ufw allow 80/tcp >/dev/null 2>&1 || true
ufw allow 443/tcp >/dev/null 2>&1 || true
ufw allow 443/udp >/dev/null 2>&1 || true   # Caddy HTTP/3
yes | ufw enable >/dev/null 2>&1 || true
systemctl enable --now fail2ban >/dev/null 2>&1 || true
ok "防火墙只放行 22/80/443；fail2ban 已开启（自动封禁 SSH 爆破）"

# ---------------------------------------------------------------- 8. 每日备份
log "8/9 配置每日自动备份（03:30，保留 7 天）"
mkdir -p /var/backups/krp
# 备份脚本随仓库分发（deploy/backup.sh），这里只安装权限与定时任务
chmod +x "$APP_DIR/deploy/backup.sh"
cat >/etc/cron.d/krp-backup <<EOF
30 3 * * * root $APP_DIR/deploy/backup.sh >> /var/log/krp-backup.log 2>&1
EOF
ok "备份脚本：$APP_DIR/deploy/backup.sh（目录 /var/backups/krp，保留 7 天）"
ok "首次备份建议手动跑一次验证：bash $APP_DIR/deploy/backup.sh"

# ---------------------------------------------------------------- 9. 汇总
log "9/9 部署完成"
IP="$(curl -fsS --max-time 5 https://api.ipify.org || echo '你的公网IP')"
if [[ -n "$DOMAIN" ]]; then
  ACCESS="https://$DOMAIN"
else
  ACCESS="http://$IP"
fi
cat <<EOF

============================================================
  部署完成 🎉

  访问地址 : $ACCESS
  （不在终端打印任何账号/验证码，避免凭据留在 shell 历史与日志里）

  常用命令（在 $APP_DIR 下）：

    查看状态   docker compose -f docker-compose.prod.yml ps
    查看日志   docker compose -f docker-compose.prod.yml logs -f app
    重启应用   docker compose -f docker-compose.prod.yml restart app
    更新代码   git pull && docker compose -f docker-compose.prod.yml up -d --build
    手动备份   bash deploy/backup.sh
    图谱控制台 ssh -L 7474:127.0.0.1:7474 root@$IP  然后浏览器打开 http://localhost:7474

  下一步：
    1) 配置真实短信服务后用自己手机号登录（演示用万能码默认已关闭）
    2) 上传一篇笔记，确认能自动抽取（需要 .env.production 里配了 LLM_API_KEY）
    3) 把这个地址填进展览馆作品的 envUrl（作者端无权限时请管理员代填）
============================================================
EOF
