FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/web/package*.json ./
RUN --mount=type=secret,id=environment_ca \
    if [ -f /run/secrets/environment_ca ]; then \
      export NODE_EXTRA_CA_CERTS=/run/secrets/environment_ca; \
    fi; npm ci
COPY apps/web ./
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
