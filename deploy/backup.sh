#!/usr/bin/env bash
# 每日备份：SQLite 数据库与上传文件 + Neo4j 图谱数据
#
# 设计说明：
#   - 关系库（SQLite/上传）在命名卷 krp-data 中，用临时容器打包（不停服）
#   - Neo4j 采用「停容器 → 打包数据卷 → 起容器」的方式，保证快照一致
#     （neo4j-admin database dump 要求数据库离线；社区版无在线备份，故用卷快照）
#   - 保留最近 7 天，自动清理更早文件
#
# 由 cron 每天 03:30 调用（见 /etc/cron.d/krp-backup），也可手动执行。
set -euo pipefail

STAMP="$(date +%F_%H%M)"
DEST="${BACKUP_DIR:-/var/backups/krp}"
mkdir -p "$DEST"

log() { echo "[$(date '+%F %T')] $*"; }

# ---------- 1) 关系库 + 上传文件 ----------
log "备份应用数据（SQLite + uploads）"
docker run --rm \
  -v krp-data:/data:ro \
  -v "$DEST":/backup \
  alpine tar czf "/backup/krp-data-$STAMP.tar.gz" -C / data \
  && log "  ✔ krp-data-$STAMP.tar.gz（$(du -h "$DEST/krp-data-$STAMP.tar.gz" | cut -f1)）" \
  || log "  ✘ 应用数据备份失败"

# ---------- 2) Neo4j 图谱（停容器保证一致性） ----------
log "备份图谱数据（短暂停止 Neo4j，约 10–20 秒）"
if docker ps --format '{{.Names}}' | grep -q '^krp-neo4j$'; then
  docker stop krp-neo4j >/dev/null
  docker run --rm \
    -v krp-neo4j:/data:ro \
    -v "$DEST":/backup \
    alpine tar czf "/backup/krp-neo4j-$STAMP.tar.gz" -C / data \
    && log "  ✔ krp-neo4j-$STAMP.tar.gz（$(du -h "$DEST/krp-neo4j-$STAMP.tar.gz" | cut -f1)）" \
    || log "  ✘ 图谱备份失败"
  docker start krp-neo4j >/dev/null
  log "  ✔ Neo4j 已恢复运行"
else
  log "  ! 未发现 krp-neo4j 容器，跳过"
fi

# ---------- 3) 清理 7 天前的备份 ----------
DELETED="$(find "$DEST" -type f -name 'krp-*' -mtime +7 -print -delete | wc -l)"
log "清理过期备份：$DELETED 个"
log "备份目录现有 $(ls -1 "$DEST" | wc -l) 个文件，占用 $(du -sh "$DEST" | cut -f1)"
log "完成"
