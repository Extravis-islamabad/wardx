# Runs a MikroTik CHR (RouterOS arm64) VM under QEMU, for WardX rotation tests only.
FROM alpine:3.20
RUN apk add --no-cache qemu-system-aarch64 qemu-img
# EDK2 UEFI firmware for the aarch64 "virt" machine ships with QEMU on Alpine.
COPY run-chr.sh /run-chr.sh
RUN chmod +x /run-chr.sh
EXPOSE 22 8728 8729
ENTRYPOINT ["/run-chr.sh"]
