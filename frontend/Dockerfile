# Frontend: dependências exatas do package-lock (npm ci), bases fixadas por digest.
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS deps
ENV NPM_CONFIG_UPDATE_NOTIFIER=false NPM_CONFIG_FUND=false NPM_CONFIG_AUDIT=false
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Testes: typecheck, lint e vitest; python3 só para o harness de mutantes (biblioteca padrão).
FROM deps AS test
RUN apk add --no-cache python3
COPY . .
CMD ["sh", "-c", "npm run typecheck && npm run lint && npm test"]

FROM deps AS build
COPY . .
RUN npm run build

# Execução: Caddy serve os estáticos e encaminha /api para o backend (mesma origem).
FROM caddy:2-alpine@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b AS runtime
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
