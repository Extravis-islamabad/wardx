#!/bin/sh
# PostgreSQL archive_command (HA_DR.md §7):
#   archive_mode = on
#   archive_command = 'WARDX_BACKEND=... WARDX_WAL_ARCHIVE_DIR=... /path/wal-archive.sh %p %f'
# Encrypts each WAL segment into the archive. Never overwrites an archived segment.
. "$(dirname "$0")/common.sh"
: "${WARDX_WAL_ARCHIVE_DIR:?set WARDX_WAL_ARCHIVE_DIR}"
src=$1; name=$2
umask 077
mkdir -p "$WARDX_WAL_ARCHIVE_DIR"
dst="$WARDX_WAL_ARCHIVE_DIR/$name.wxbak"
[ ! -f "$dst" ] || { echo "already archived: $name" >&2; exit 1; }
wardx backup encrypt --name "$name" --in "$src" --out "$dst.part"
mv "$dst.part" "$dst"
