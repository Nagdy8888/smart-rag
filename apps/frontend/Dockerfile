# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS deps
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/frontend/package.json apps/frontend/package.json
RUN pnpm install --frozen-lockfile --filter smart-rag-frontend...

FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS build
WORKDIR /repo
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/frontend/node_modules ./apps/frontend/node_modules
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/frontend ./apps/frontend
RUN pnpm --filter smart-rag-frontend build

FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/.next/standalone ./
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/.next/static ./apps/frontend/.next/static
COPY --from=build --chown=appuser:appuser /repo/apps/frontend/public ./apps/frontend/public
USER 10001:10001
EXPOSE 3000
CMD ["node", "apps/frontend/server.js"]
