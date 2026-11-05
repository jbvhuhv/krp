#!/usr/bin/env bash
# ============================================================
#  KRP - start backend (macOS / Linux, portable)
#  1) locate repo by this script's own path
#  2) detect Python (PYTHON_CMD -> python3 -> python)
#  3) ensure logs/ exists, then start uvicorn
#  Override interpreter with: PYTHON_CMD=... ./scripts/run_backend.sh
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

PYTHON="${PYTHON_CMD:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  done
fi
if [ -z "$PYTHON" ]; then
  echo "[ERROR] Python 3.12+ not found. Install it, or set PYTHON_CMD, then retry."
  exit 1
fi

mkdir -p "$ROOT/logs"
# 默认只绑本机回环：配合 backend/.env 的 ALLOW_DEV_LOGIN（万能验证码仅对白名单手机号生效），
# 绑 0.0.0.0 会让同网段任何人都能用演示手机号 + 123456 登录。
# 需要手机/局域网访问时显式开启：HOST=0.0.0.0 ./scripts/run_backend.sh
HOST="${HOST:-127.0.0.1}"
echo "[OK] Python : $PYTHON"
echo "[OK] Backend: $BACKEND"
echo "[OK] Listen : $HOST:8000"
echo "[OK] Logs   : $ROOT/logs/be_out.log"

cd "$BACKEND"
exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port 8000 \
  >> "$ROOT/logs/be_out.log" 2>> "$ROOT/logs/be_err.log"
