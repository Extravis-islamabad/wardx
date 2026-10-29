#!/bin/sh
# PostgreSQL restore_command for point-in-time recovery (HA_DR.md §7):
#   restore_command = 'WARDX_BACKEND=... WARDX_WAL_ARCHIVE_DIR=... /path/wal-restore.sh %f %p'
#   recovery_target_time = '2026-10-29 12:00:00+00'
. "$(dirname "$0")/common.sh"
: "${WARDX_WAL_ARCHIVE_DIR:?set WARDX_WAL_ARCHIVE_DIR}"
name=$1; dst=$2
src="$WARDX_WAL_ARCHIVE_DIR/$name.wxbak"
[ -f "$src" ] || exit 1
wardx backup decrypt --in "$src" --out "$dst"
