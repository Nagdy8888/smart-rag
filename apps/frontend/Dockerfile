FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS build
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

FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/.next/standalone ./
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/.next/static ./apps/frontend/.next/static
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/public ./apps/frontend/public
USER 10001:10001
EXPOSE 3000
CMD ["node", "apps/frontend/server.js"]
