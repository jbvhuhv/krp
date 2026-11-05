#!/usr/bin/env bash
# ============================================================
#  KRP - one-click environment setup (macOS / Linux)
#  1) locate Python / Node
#  2) install backend (pip) and frontend (npm) dependencies
#  3) create backend/.env from .env.example when missing
#  4) print Neo4j startup hints
#  Override the interpreter with: PYTHON_CMD=... ./scripts/setup.sh
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo "=== KRP one-click setup ==="

# ---------- locate Python ----------
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
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "[WARN] detected Python < 3.12, continuing anyway (project targets 3.12+)"
fi
echo "[OK] Python: $PYTHON"

# ---------- locate Node / npm ----------
if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] Node.js / npm not found. Install Node 18+ then retry."
  exit 1
fi
echo "[OK] npm found."

# ---------- backend dependencies ----------
echo "[1/4] Installing backend requirements ..."
( cd "$BACKEND" && "$PYTHON" -m pip install -r requirements.txt )

# ---------- backend .env ----------
echo "[2/4] Preparing backend/.env ..."
if [ ! -f "$BACKEND/.env" ]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  echo "[OK] created backend/.env from .env.example - fill in your API keys."
else
  echo "[SKIP] backend/.env already exists."
fi

# ---------- frontend dependencies ----------
echo "[3/4] Installing frontend dependencies ..."
( cd "$FRONTEND" && npm install )

# ---------- Neo4j reminder ----------
echo "[4/4] Neo4j is required. Start it with Docker:"
echo "   docker compose up -d neo4j   (先在仓库根目录建 .env 并写入 NEO4J_PASSWORD)"
echo "   没有图数据库也能启动：应用会自动降级为内置只读演示图谱"

echo
echo "=== setup finished ==="
echo "  backend : ./scripts/run_backend.sh"
echo "  frontend: cd frontend && npm run dev"
