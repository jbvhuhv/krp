#!/usr/bin/env bash
# 给已部署的环境补上域名与 HTTPS（买了域名之后执行）
#
# 用法：DOMAIN=krp.example.com bash deploy/renew-domain.sh
# 前置：域名 A 记录已指向服务器公网 IP（解析生效后再执行，否则证书申请会失败）
set -euo pipefail

DOMAIN="${DOMAIN:-}"
[[ -n "$DOMAIN" ]] || { echo "用法：DOMAIN=你的域名 bash $0"; exit 1; }
[[ $EUID -eq 0 ]] || { echo "请用 root 运行"; exit 1; }

echo "==> 检查域名解析是否已指向本机"
IP="$(curl -fsS --max-time 5 https://api.ipify.org || true)"
RESOLVED="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"
echo "    本机公网 IP : $IP"
echo "    域名解析到  : ${RESOLVED:-（未解析）}"
if [[ -n "$RESOLVED" && "$RESOLVED" != "$IP" ]]; then
  echo "    ! 域名尚未指向本机，证书申请会失败。请先改 DNS A 记录，等生效后重跑。"
  exit 1
fi

echo "==> 写入 Caddyfile（自动申请并续期证书）"
cat >/etc/caddy/Caddyfile <<EOF
$DOMAIN {
    encode gzip zstd
    reverse_proxy 127.0.0.1:8000
}
EOF
systemctl reload caddy 2>/dev/null || systemctl restart caddy
sleep 5
systemctl is-active --quiet caddy && echo "    ✔ Caddy 运行中" || { echo "    ✘ Caddy 启动失败"; journalctl -u caddy -n 30 --no-pager; exit 1; }

echo "==> 验证访问"
curl -fsS -o /dev/null -w "    https://$DOMAIN → HTTP %{http_code}（%{time_total}s）\n" "https://$DOMAIN/health?deep=1" || echo "    ! 证书可能还在申请中，1 分钟后重试：curl -I https://$DOMAIN"

echo
echo "完成。把 https://$DOMAIN 填进展览馆作品的 envUrl 即可。"
