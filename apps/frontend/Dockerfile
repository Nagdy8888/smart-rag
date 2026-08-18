FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS build
WORKDIR /repo
ENV PUPPETEER_SKIP_DOWNLOAD=1 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    CI=1 \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/frontend ./apps/frontend
RUN pnpm install --frozen-lockfile --filter smart-rag-frontend... \
    && pnpm --filter smart-rag-frontend build

FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# Alpine security updates as root before dropping to UID 10001.
# Runtime does not use npm; remove the image-bundled copy (CVE-2026-59873).
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -rf /usr/local/lib/node_modules/corepack \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
    && adduser -D -u 10001 -s /sbin/nologin appuser
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/.next/standalone ./
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/.next/static ./apps/frontend/.next/static
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/public ./apps/frontend/public
USER 10001:10001
EXPOSE 3000
CMD ["node", "apps/frontend/server.js"]
