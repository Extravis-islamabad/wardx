#!/bin/sh
# Boots the CHR image mounted at /images, on a throwaway overlay so the
# pristine image is never modified. Guest ports reach the container via
# QEMU user networking; the container publishes them to 127.0.0.1 only.
set -eu
BASE=/images/${CHR_IMAGE:-chr-7.25-arm64.img}
OVERLAY=/tmp/chr-overlay.qcow2
qemu-img create -q -f qcow2 -F raw -b "$BASE" "$OVERLAY"
FW=$(ls /usr/share/qemu/edk2-aarch64-code.fd)
exec qemu-system-aarch64 \
  -machine virt -cpu cortex-a72 -smp 2 -m 512 \
  -bios "$FW" \
  -drive file="$OVERLAY",if=virtio,format=qcow2 \
  -netdev user,id=n0,hostfwd=tcp::22-:22,hostfwd=tcp::8728-:8728,hostfwd=tcp::8729-:8729 \
  -device virtio-net-pci,netdev=n0 \
  -nographic -serial mon:stdio
