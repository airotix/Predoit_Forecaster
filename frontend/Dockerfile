# Preduit frontend — Next.js 14 (standalone output). Multi-stage for a small runtime image.
# NEXT_PUBLIC_* values are baked in at BUILD time, so they are passed as build args.

# ---- deps ----
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install

# ---- build ----
FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Browser-exposed configuration (embedded at build time).
ARG NEXT_PUBLIC_API_URL=http://localhost:4000/api
ARG NEXT_PUBLIC_AUTH_ENABLED=false
ARG NEXT_PUBLIC_AUTH_DEV_ROLE=admin
ARG NEXT_PUBLIC_AZURE_CLIENT_ID=
ARG NEXT_PUBLIC_AZURE_TENANT_ID=
ARG NEXT_PUBLIC_AZURE_API_SCOPE=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_AUTH_ENABLED=$NEXT_PUBLIC_AUTH_ENABLED \
    NEXT_PUBLIC_AUTH_DEV_ROLE=$NEXT_PUBLIC_AUTH_DEV_ROLE \
    NEXT_PUBLIC_AZURE_CLIENT_ID=$NEXT_PUBLIC_AZURE_CLIENT_ID \
    NEXT_PUBLIC_AZURE_TENANT_ID=$NEXT_PUBLIC_AZURE_TENANT_ID \
    NEXT_PUBLIC_AZURE_API_SCOPE=$NEXT_PUBLIC_AZURE_API_SCOPE \
    NEXT_TELEMETRY_DISABLED=1
# Ensure public/ exists even if the app ships without static assets.
RUN mkdir -p public && npm run build

# ---- runner ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Non-root runtime user.
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Standalone server + static assets + public files.
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
