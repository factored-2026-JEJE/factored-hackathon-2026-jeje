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

Na primeira vez o `make up` baixa o dataset dos organizadores (~1,6 GB, ~5 min), confere cada
arquivo pelo manifesto versionado em `data/manifesto/` e carrega o banco. Depois sobe em segundos.
Sem as chaves? `make up-fixture` sobe com um dataset sintético pequeno.

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

- `data/manifesto/` — versão dos dados (hash de cada arquivo); `data/fixture/` — dataset sintético.

Estado atual: fundação e dados brutos carregados (camada raw). O atendimento ainda não está
implementado.
