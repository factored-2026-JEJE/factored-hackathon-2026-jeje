# jeje-product-v1

Atendimento bancário em espanhol e português do time **JEJE** (Jader, Erik, João e Enzo) —
Factored AI & Data Hackathon 2026.

O cliente conversa sobre as próprias transações: entende por que uma compra foi recusada ou está
pendente e registra um pedido de revisão (pré-caso) de cobrança que não reconhece. Fraude, pedido
de atendente e casos fora da regra vão para a fila humana com um resumo pronto. Quem decide é uma
política determinística com fatos do banco; o texto do cliente nunca muda permissão.

## Ligar tudo

Precisa só de **Docker**.

```bash
cp .env.example .env   # cole as chaves do dataset (página 2 do dicionário)
make up                # ou: docker compose up -d --build --wait
```

Abra **http://localhost:8080**, entre como um cliente de demonstração e converse.

Na primeira vez o `make up` baixa o dataset dos organizadores (~1,6 GB, ~5 min), confere cada
arquivo pelo manifesto versionado em `data/manifesto/` e carrega o banco. Depois sobe em segundos.
Sem as chaves? `make up-fixture` sobe com um dataset sintético pequeno.

## Experimente

- **Contestar:** "No reconozco el cobro de 45,90 del 10/03/2025" (use valor e data de uma
  transação da sua lista) → o assistente mostra a transação e pede confirmação; "Sí, confirmo"
  registra o pré-caso e devolve o protocolo.
- **Perguntar:** "¿Por qué rechazaron mi compra?" → se houver mais de uma, ele lista e você escolhe.
- **Pedir um humano:** "Me robaron la tarjeta" → o caso aparece na fila do atendente, que o assume.

Em português também: "Não reconheço a cobrança…", "Por que recusaram minha compra?", "Roubaram
meu cartão". As métricas do atendimento (encaminhamentos, pré-casos, latência) ficam ao lado.

## Modelo local (opcional)

A conversa funciona sem modelo. Com `INTERPRETADOR: "ollama"` no `compose.yaml`, as frases que as
regras não entendem vão para um modelo local (Ollama, `qwen2.5:7b` por padrão), que só classifica:
sim/não, fraude e identificadores continuam com as regras, e a política decide o que fazer. Modelo
fora do ar ou saída inválida → segue pelas regras, e o trace do turno diz quem leu a mensagem. O
Ollama do host precisa aceitar conexões dos containers (ex.: `OLLAMA_HOST=0.0.0.0:11434`).

## Logs

`make logs` mostra uma linha por acontecimento, marcada com o id da requisição:

```text
INFO jeje.conversa req=7489ce07… turno conversa=6nP-Nrp2jajGqdYt3AxszA numero=2 intencao=fraude regra=POL-HUM-01 acao=humano estado=com_humano efeito=AT-00000003
INFO jeje.http req=7489ce07… acesso metodo=POST rota=/conversas/{conversa_id}/turnos status=200 ms=13.7
WARNING jeje.db req=b0711da3… banco indisponivel erro=OperationalError motivo="failed to resolve host 'db'…"
```

- Toda resposta traz `X-Request-ID` (um id válido recebido é reaproveitado): quem relata um problema
  informa esse id, e ele leva às linhas do log.
- Nível em `LOG_LEVEL` no `compose.yaml`; `DEBUG` mostra também as sondas de saúde.
- Nunca entram a mensagem do cliente, o token, o identificador do cliente nem valores de SQL. Erro
  inesperado vira 500 com o id e um log com os arquivos e as linhas do código, sem a mensagem da
  exceção (o banco repete valores nela). O trace completo de cada turno fica em `app.eventos`
  (`make metricas`).
- Banco fora do ar: 503 com `Retry-After`, sem traceback.

## Testar

```bash
make check          # segredos + lint + testes + mutantes (cada teste precisa pegar um defeito real)
make e2e            # jornadas no navegador (Chromium e Firefox) contra a stack no ar
make gate           # check + e2e + mutantes de ponta a ponta
make metricas       # métricas recomputadas dos eventos de cada turno
scripts/repro.sh    # do zero: clone limpo, stack isolada com a fixture, todos os gates
```

## Onde fica cada coisa

- `compose.yaml` — **toda** a configuração não secreta (flags, limites, portas, testes).
  `.env` guarda só segredos e nunca vai para o Git.
- `backend/` — API (FastAPI) e migrations. Regras em `politica.py`, conversa em `conversa.py`,
  textos aprovados ES/PT em `mensagens.py`.
- `frontend/` — interface React; tipos gerados de `contrato/openapi.json` (`make contrato`).
- `e2e/` — jornadas no navegador; `mutantes/` — defeitos deliberados que os testes precisam pegar.
- `data/manifesto/` — versão dos dados (hash de cada arquivo); `data/fixture/` — dataset sintético.

## Limites

- Política **simulada** e rotulada, com limites decididos pelo time (todos no `compose.yaml`): o
  assistente registra sozinho a contestação de transação aprovada até USD 5.000; à noite
  (20h–6h) pelo app ou pela web, até USD 1.000 por transação e 1.000 somados no dia (a base não
  diz se o aparelho é cadastrado, então todo acesso digital noturno conta como não cadastrado);
  transferência acima de USD 50.000 vai para análise de segurança. O resto vai para humano.
- Pré-caso é pedido de revisão: não move dinheiro nem promete prazo ou resultado.
- Motivo de recusa usa o significado genérico dos códigos ISO 8583, rotulado como tal.
- Acesso por cliente de demonstração (sem senha) e console do atendente existem só com
  `MODO_DEMO` ligado; num banco real, os dois exigiriam autenticação.
