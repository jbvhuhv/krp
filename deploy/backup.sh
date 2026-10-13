#!/usr/bin/env bash
# 每日备份：SQLite 数据库与上传文件 + Neo4j 图谱数据
#
# 设计说明：
#   - 卷名由「运行中的容器挂载」反查得到（compose 会给卷加项目名前缀，写死名字会备份到空卷）
#   - 关系库（SQLite/上传）在卷 krp-data 中，用临时容器打包（不停服）
#   - Neo4j 采用「停容器 → 打包数据卷 → 起容器」的方式保证快照一致
#     （社区版无在线备份，neo4j-admin database dump 要求数据库离线）
#   - 保留最近 N 天（默认 7），自动清理更早文件
#
# 手动执行：bash deploy/backup.sh        （可加 KEEP_DAYS=3 调整保留天数）
set -euo pipefail

STAMP="$(date +%F_%H%M)"
DEST="${BACKUP_DIR:-/var/backups/krp}"
KEEP_DAYS="${KEEP_DAYS:-7}"
APP_CONTAINER="${APP_CONTAINER:-krp-app}"
NEO_CONTAINER="${NEO_CONTAINER:-krp-neo4j}"
mkdir -p "$DEST"

log() { echo "[$(date '+%F %T')] $*"; }

volume_of() {  # $1=容器名 $2=容器内挂载点
  docker inspect "$1" --format "{{range .Mounts}}{{if eq .Destination \"$2\"}}{{.Name}}{{end}}{{end}}" 2>/dev/null
}

DATA_VOL="$(volume_of "$APP_CONTAINER" /data)"
NEO_VOL="$(volume_of "$NEO_CONTAINER" /data)"

if [[ -z "$DATA_VOL" ]]; then
  log "✘ 无法确定应用数据卷（容器 $APP_CONTAINER 未运行？）"
  exit 1
fi

# ---------- 1) 关系库 + 上传文件 ----------
log "备份应用数据：卷 $DATA_VOL"
docker run --rm -v "$DATA_VOL":/data:ro -v "$DEST":/backup alpine \
  tar czf "/backup/krp-data-$STAMP.tar.gz" -C / data \
  && log "  ✔ krp-data-$STAMP.tar.gz（$(du -h "$DEST/krp-data-$STAMP.tar.gz" | cut -f1)）" \
  || log "  ✘ 应用数据备份失败"

# ---------- 2) Neo4j 图谱（停容器保证一致性） ----------
if [[ -n "$NEO_VOL" ]] && docker ps --format '{{.Names}}' | grep -qx "$NEO_CONTAINER"; then
  log "备份图谱数据：卷 $NEO_VOL（短暂停止 Neo4j）"
  docker stop "$NEO_CONTAINER" >/dev/null
  docker run --rm -v "$NEO_VOL":/data:ro -v "$DEST":/backup alpine \
    tar czf "/backup/krp-neo4j-$STAMP.tar.gz" -C / data \
    && log "  ✔ krp-neo4j-$STAMP.tar.gz（$(du -h "$DEST/krp-neo4j-$STAMP.tar.gz" | cut -f1)）" \
    || log "  ✘ 图谱备份失败"
  docker start "$NEO_CONTAINER" >/dev/null
  log "  ✔ Neo4j 已重新启动（约 30 秒后恢复服务）"
else
  log "  ! 未找到运行中的 $NEO_CONTAINER，跳过图谱备份"
fi

# ---------- 3) 清理过期备份 ----------
DELETED="$(find "$DEST" -type f -name 'krp-*' -mtime +"$KEEP_DAYS" -print -delete | wc -l)"
log "清理 ${KEEP_DAYS} 天前的备份：$DELETED 个"
log "备份目录现有 $(ls -1 "$DEST" | wc -l) 个文件，占用 $(du -sh "$DEST" | cut -f1)"
log "完成"
