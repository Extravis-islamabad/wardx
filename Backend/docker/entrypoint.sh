#!/bin/sh
# Container entrypoint: prepares /data, then runs the role WARDX_APP_ROLE asks for.
set -eu

mkdir -p "${WARDX_RECORDING_DIR:-/data/recordings}"

# The gateway needs a stable SSH host key. If none was mounted, create one once on the
# persistent volume so users' known_hosts keep matching across restarts.
if [ "${WARDX_APP_ROLE:-api}" = "gateway" ]; then
  : "${WARDX_GATEWAY_HOST_KEY_FILE:=/data/keys/gateway_host_key}"
  export WARDX_GATEWAY_HOST_KEY_FILE
  if [ ! -s "$WARDX_GATEWAY_HOST_KEY_FILE" ]; then
    echo "wardx: generating gateway host key at $WARDX_GATEWAY_HOST_KEY_FILE"
    python - "$WARDX_GATEWAY_HOST_KEY_FILE" <<'PY'
import os, sys, asyncssh
path = sys.argv[1]
os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
key = asyncssh.generate_private_key("ssh-ed25519")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "wb") as fh:
    fh.write(key.export_private_key())
PY
  fi
fi

exec "$@"
