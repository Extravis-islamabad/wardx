#!/bin/sh
# One-time setup for a fresh WardX clone: installs the pinned gitleaks binary
# (checksum-verified) into ~/.local/bin and turns on the repo's git hooks.
#   sh scripts/dev-setup.sh
set -eu

GITLEAKS_VERSION="8.24.3"
# From gitleaks_8.24.3_checksums.txt; bump together with the version
# (and in .github/workflows/gitleaks.yml).
SHA_darwin_arm64="b90f13bb8c90ab72083d9b0c842e39dafb82c0e5c3f872f407366b7a58909013"
SHA_darwin_x64="41c44ae8ad1d6eef57d4526ad0fd67d8129eee9a856f55c2b3b9395fd3d9ec0f"
SHA_linux_x64="9991e0b2903da4c8f6122b5c3186448b927a5da4deef1fe45271c3793f4ee29c"
SHA_linux_arm64="5f2edbe1f49f7b920f9e06e90759947d3c5dfc16f752fb93aaafc17e9d14cf07"

repo_root=$(git rev-parse --show-toplevel)
bin_dir="${HOME}/.local/bin"

case "$(uname -s)" in
  Darwin) os=darwin ;;
  Linux) os=linux ;;
  *) echo "Unsupported OS; install gitleaks ${GITLEAKS_VERSION} yourself." >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64 | aarch64) arch=arm64 ;;
  x86_64 | amd64) arch=x64 ;;
  *) echo "Unsupported CPU; install gitleaks ${GITLEAKS_VERSION} yourself." >&2; exit 1 ;;
esac

if command -v gitleaks >/dev/null 2>&1 && gitleaks version | grep -q "${GITLEAKS_VERSION}"; then
  echo "gitleaks ${GITLEAKS_VERSION} already installed"
else
  eval "expected=\${SHA_${os}_${arch}}"
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  archive="gitleaks_${GITLEAKS_VERSION}_${os}_${arch}.tar.gz"
  curl -sSLo "$tmp/$archive" \
    "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${archive}"
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$tmp/$archive" | cut -d' ' -f1)
  else
    actual=$(shasum -a 256 "$tmp/$archive" | cut -d' ' -f1)
  fi
  if [ "$actual" != "$expected" ]; then
    echo "Checksum mismatch for $archive; not installing." >&2
    exit 1
  fi
  mkdir -p "$bin_dir"
  tar xzf "$tmp/$archive" -C "$tmp" gitleaks
  install -m 0755 "$tmp/gitleaks" "$bin_dir/gitleaks"
  echo "Installed gitleaks ${GITLEAKS_VERSION} to $bin_dir (make sure it is on PATH)"
fi

git -C "$repo_root" config core.hooksPath .githooks
echo "Git hooks enabled (core.hooksPath=.githooks): commits are scanned for secrets."
