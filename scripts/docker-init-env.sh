#!/bin/sh
# Create .env from .env.docker.example with freshly generated secrets.
# Refuses to overwrite an existing .env.
set -eu
cd "$(dirname "$0")/.."
[ -e .env ] && { echo ".env already exists; not overwriting" >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }

pg=$(openssl rand -hex 24)
jwt=$(openssl rand -base64 48 | tr -d '\n')
kek=$(openssl rand -base64 32 | tr -d '\n')
admin=$(openssl rand -base64 18 | tr -d '\n/+=')

sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$pg|" \
    -e "s|^WARDX_JWT_SECRET=.*|WARDX_JWT_SECRET=$jwt|" \
    -e "s|^WARDX_VAULT_KEK=.*|WARDX_VAULT_KEK=$kek|" \
    -e "s|^WARDX_BOOTSTRAP_ADMIN_PASSWORD=.*|WARDX_BOOTSTRAP_ADMIN_PASSWORD=$admin|" \
    .env.docker.example > .env
chmod 600 .env
echo "Wrote .env (mode 600)."
echo "Initial admin password: $admin"
echo "Back up WARDX_VAULT_KEK offline now; without it the vault cannot be opened."
