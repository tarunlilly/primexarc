# PrimeXarc shell — static SPA served by nginx.
# No backend. Runtime env vars injected by docker/entrypoint.sh.

FROM node:20-alpine AS builder
WORKDIR /app

COPY .npmrc ./
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 4000
ENTRYPOINT ["/entrypoint.sh"]
