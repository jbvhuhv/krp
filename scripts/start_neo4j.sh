#!/usr/bin/env bash
# ============================================================
#  KRP - start the bundled local Neo4j (macOS / Linux)
#  1) locate repo by this script's own path
#  2) detect Java (JAVA_CMD -> JAVA_HOME -> deps/jdk21/* -> PATH)
#  3) start deps/neo4j-build via CommunityEntryPoint (foreground)
#  Override interpreter with: JAVA_CMD=/path/to/java ./scripts/start_neo4j.sh
#
#  说明：deps/ 是作者开发机保留的构建产物（已被 .gitignore 的 /deps/ 排除），
#  不含官方发行版的 bin/ 脚本，因此不能 `neo4j start`，只能直接拉起 JVM。
#  新克隆的仓库没有 deps/，请改用 Docker：docker compose up -d neo4j
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NEO4J_HOME="$ROOT/deps/neo4j-build"
TARGET="$NEO4J_HOME/target"
LOG="$ROOT/logs/neo4j.log"

if [ ! -d "$TARGET/lib" ]; then
  echo "[ERROR] 未找到本地 Neo4j 运行时：$TARGET/lib"
  echo "        该目录不随仓库分发（.gitignore 的 /deps/），新克隆的仓库没有它。"
  echo "        请改用 Docker：docker compose up -d neo4j"
  exit 1
fi
if [ ! -f "$TARGET/conf/neo4j.conf" ]; then
  echo "[ERROR] 缺少配置：$TARGET/conf/neo4j.conf"
  exit 1
fi

# ---------- locate Java ----------
JAVA="${JAVA_CMD:-}"
if [ -z "$JAVA" ] && [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
  JAVA="$JAVA_HOME/bin/java"
fi
if [ -z "$JAVA" ]; then
  for candidate in "$ROOT"/deps/jdk21/*/bin/java; do
    if [ -x "$candidate" ]; then JAVA="$candidate"; break; fi
  done
fi
if [ -z "$JAVA" ] && command -v java >/dev/null 2>&1; then
  JAVA="$(command -v java)"
fi
if [ -z "$JAVA" ]; then
  echo "[ERROR] Java 17+ not found. Install a JDK, or set JAVA_CMD, then retry."
  exit 1
fi

# ---------- already running? ----------
if (exec 3<>/dev/tcp/127.0.0.1/7687) 2>/dev/null; then
  echo "[SKIP] Bolt 7687 已在监听，Neo4j 看起来已经在跑。"
  echo "       需要重启的话，先停掉占用 7687 的 java 进程。"
  exit 0
fi

mkdir -p "$ROOT/logs"
echo "[OK] Java : $JAVA"
echo "[OK] Home : $TARGET"
echo "[OK] Logs : $LOG"
echo "[OK] Bolt : 7687 / HTTP : 7474"
echo "[..] 启动中，前台运行；按 Ctrl+C 停止。"
echo "     本地 conf 关闭了认证（dbms.security.auth_enabled=false），密码不参与校验。"
echo

cd "$NEO4J_HOME"
# 与手工验证过的启动方式保持一致：lib 用通配符交给 JVM 展开
exec "$JAVA" -cp "target/lib/*" org.neo4j.server.CommunityEntryPoint \
  --home-dir=target --config-dir=target/conf 2>&1 | tee -a "$LOG"
