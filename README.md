# jeje-product-v1

Produto do time **JEJE** (Jader, Erik, João e Enzo) para o Factored AI & Data Hackathon 2026: atendimento bancário ES/PT com política determinística, IA via contratos e handoff humano.

> Estado: fundação inicial. Nenhuma funcionalidade de atendimento implementada ainda.

## Estrutura

- `backend/` — Python 3.12 + FastAPI + Pydantic (pacote `jeje`).

Frontend (React + TypeScript + Vite), PostgreSQL e Docker Compose entram nos próximos incrementos.

## Rodar

Pré-requisito: Python 3.12.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest                                   # testes
uvicorn jeje.api:app --reload            # API em http://127.0.0.1:8000/health
```

No PC de desenvolvimento do time há um ambiente pronto: `source <vault>/scripts/ambiente/ativar.sh`, depois `cd backend && pytest`.
