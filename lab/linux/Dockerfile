# Throwaway Linux SSH target for WardX rotation tests. Accounts are created per
# test run (wardx_rot_*); nothing here is a real or shared machine.
FROM debian:12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-server sudo passwd \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /run/sshd \
 && sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?KbdInteractiveAuthentication .*/KbdInteractiveAuthentication yes/' /etc/ssh/sshd_config \
 && sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
