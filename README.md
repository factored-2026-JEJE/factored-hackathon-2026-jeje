# jeje-product-v1

Atendimento bancário em espanhol e português do time **JEJE** (Jader, Erik, João e Enzo) —
Factored AI & Data Hackathon 2026.

## Ligar tudo

Precisa só de **Docker**.

```bash
cp .env.example .env   # cole as chaves do dataset (página 2 do dicionário)
make up                # ou: docker compose up -d --build --wait
```

Abra **http://localhost:8080**.

## Testar

```bash
make check   # lint + testes + prova de que cada teste pega um defeito real (mutantes)
make gate    # check + jornadas no navegador + mutantes de ponta a ponta
```

## Onde fica cada coisa

- `compose.yaml` — **toda** a configuração não secreta (flags, portas, timeouts, testes).
  `.env` guarda só segredos e nunca vai para o Git.
- `backend/` — API Python (FastAPI) e migrations (Alembic).
- `frontend/` — interface React; tipos gerados de `contrato/openapi.json` (`make contrato`).
- `e2e/` — jornadas no navegador (Playwright, Chromium e Firefox).
- `mutantes/` — defeitos deliberados que cada teste precisa detectar.

Estado atual: fundação (API, banco, interface de status e testes). O atendimento ainda não está
implementado.
