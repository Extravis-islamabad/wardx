#!/bin/sh
# WardX rotation lab. Touches ONLY containers named wardx-lab-* on the
# wardx-lab network; never prunes or stops anything else on this Docker host.
#   sh lab/lab.sh build | up-mikrotik | status | down
set -eu
LAB=$(cd "$(dirname "$0")" && pwd)
case "${1:-status}" in
  build)
    docker build -q -t wardx-lab/linux-ssh:1 "$LAB/linux"
    docker build -q -t wardx-lab/mikrotik-chr:7.25 "$LAB/mikrotik" ;;
  up-mikrotik)
    [ -f "$LAB/mikrotik/images/chr-7.25-arm64.img" ] || { echo "missing CHR image; see lab/README.md" >&2; exit 1; }
    docker network inspect wardx-lab >/dev/null 2>&1 || docker network create wardx-lab >/dev/null
    docker run -d --name wardx-lab-mikrotik --network wardx-lab \
      -p 127.0.0.1:2232:22 -p 127.0.0.1:8738:8728 -p 127.0.0.1:8739:8729 \
      -v "$LAB/mikrotik/images:/images:ro" wardx-lab/mikrotik-chr:7.25 ;;
  status)
    docker ps -a --filter name=^/wardx-lab- --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' ;;
  down)
    for c in $(docker ps -aq --filter name=^/wardx-lab-); do docker rm -f "$c" >/dev/null; done
    echo "removed wardx-lab-* containers" ;;
  *) echo "usage: $0 build|up-mikrotik|status|down" >&2; exit 2 ;;
esac
