#!/bin/sh
# Creates the accounts a test asks for, then runs sshd in the foreground.
#   LAB_USERS="name:password[:sudo] ..."   e.g. "wardx_rot_a:pw1 wardx_rot_admin:pw2:sudo"
set -eu
ssh-keygen -A >/dev/null
for spec in ${LAB_USERS:-}; do
  name=${spec%%:*}; rest=${spec#*:}; pw=${rest%%:*}; flag=${rest#"$pw"}
  case "$name" in wardx_rot_*) ;; *) echo "refusing non-lab user name: $name" >&2; exit 1;; esac
  id "$name" >/dev/null 2>&1 || useradd -m -s /bin/bash "$name"
  printf '%s:%s\n' "$name" "$pw" | chpasswd
  if [ "$flag" = ":sudo" ]; then
    echo "$name ALL=(root) NOPASSWD: /usr/sbin/chpasswd" > "/etc/sudoers.d/$name"
    chmod 0440 "/etc/sudoers.d/$name"
  fi
done
exec /usr/sbin/sshd -D -e
