# WardX web console: build with Node, serve the static bundle with nginx,
# which also proxies /api to the backend so the browser sees one origin.
FROM node:20-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
# Upstream for /api; override with the backend's address.
ENV WARDX_API_UPSTREAM=http://api:8000
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
