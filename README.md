# jeje-product-v1

Atendimento bancário em espanhol e português do time **JEJE** (Jader, Erik, João e Enzo) —
Factored AI & Data Hackathon 2026.

O cliente conversa sobre as próprias transações: entende por que uma compra foi recusada ou está
pendente e registra um pedido de revisão (pré-caso) de cobrança que não reconhece. Fraude, pedido
de atendente e casos fora da regra vão para a fila humana com um resumo pronto. Quem decide é uma
política determinística com fatos do banco; o texto do cliente nunca muda permissão.

## Por que este fluxo

Medido na base do desafio (seção “Por que este fluxo” da interface, com a consulta de cada número;
`GET /dados/eda`):

- Contatos de motivo **transacional** são **35,0%** dos 686.296 atendimentos e **24,0%** do tempo
  total de atendimento, e **91,5%** se resolvem no primeiro contato: são perguntas com resposta nos
  dados.
- Das 4.425.008 transações, 5,0% foram recusadas, 2,0% estão pendentes e 1,0% foram estornadas;
  95% das recusas trazem código de resposta.
- Das reclamações sobre transações (20,2% de 67.095), **90,6%** são “Cargo no reconocido”.

O assistente automatiza exatamente isso: explica a situação de uma transação do próprio cliente e
registra o pedido de revisão (pré-caso) de uma cobrança não reconhecida, sempre com confirmação
explícita. Com os limites da política, 86,3% das transações aprovadas em USD da base poderiam ter a
contestação registrada sem atendente; o resto vai para um atendente com o resumo pronto. A base não
tem conversas em português (transcrições 100% em espanhol): os casos em português são do time.

## Como funciona

```mermaid
flowchart LR
  navegador[Navegador<br/>React] -->|/api| caddy[Caddy]
  caddy --> api[API FastAPI]
  api --> sessao[Sessão de teste<br/>quem é o cliente]
  api --> leitura[Leitura da mensagem<br/>regras primeiro]
  leitura -. só o que as regras<br/>não entendem .-> leitor[Leitor e5<br/>na própria API]
  leitura -. opcional .-> ollama[(Ollama do host<br/>pela ponte)]
  api --> politica[Política determinística<br/>regras POL-*]
  politica --> acoes[Consulta · pré-caso<br/>encaminhamento]
  acoes --> banco[(PostgreSQL<br/>curada + atendimento<br/>+ eventos)]
  seed[Seed: S3 → manifesto<br/>→ raw → curada] --> banco
```

Toda consulta e ação leva o cliente da sessão (dado de outro cliente é igual a inexistente). O texto
do cliente só escolhe a pergunta feita à política; o modelo só classifica, nunca decide nem executa.
Efeito (pré-caso) só com um “sim” explícito ligado à proposta, gravado sem duplicar e relido antes
de responder.

## Ligar tudo

Precisa só de **Docker**.

```bash
cp .env.example .env   # cole as chaves do dataset (página 2 do dicionário)
make up                # ou: docker compose --profile modelo up -d --build --wait
```

Abra **http://localhost:8080**, entre como um cliente de demonstração e converse.

Na primeira vez o `make up` baixa o dataset dos organizadores (~1,6 GB, ~5 min), confere cada
arquivo pelo manifesto versionado em `data/manifesto/` e carrega o banco. O build da imagem também
baixa o leitor (torch só-CPU e pesos do e5, ~2 GB) e o treina (~11 min em CPU); a imagem da API
fica com ~3,9 GB. Depois sobe em segundos.
Sem as chaves? `make up-fixture` sobe com um dataset sintético pequeno.

## Experimente

- **Contestar:** "No reconozco el cobro de 45,90 del 10/03/2025" (use valor e data de uma
  transação da sua lista) → o assistente mostra a transação e pede confirmação; "Sí, confirmo"
  registra o pré-caso e devolve o protocolo.
- **Perguntar:** "¿Por qué rechazaron mi compra?" → se houver mais de uma, ele lista e você escolhe.
- **Pedir um humano:** "Me robaron la tarjeta" → o caso aparece na fila do atendente, que o assume.

Em português também: "Não reconheço a cobrança…", "Por que recusaram minha compra?", "Roubaram
meu cartão". As métricas do atendimento (encaminhamentos, pré-casos, latência) ficam ao lado.

## Testar em grupo (Codespace e reviews)

O time conversa com o assistente num site só dele e avalia cada conversa; cada avaliação vira uma
Issue neste repositório, com a transcrição, para o erro ser discutido e corrigido.

1. **Subir:** Code > Codespaces > *Create codespace on …* (máquina de 4 núcleos). O
   `.devcontainer/subir.sh` sobe a stack sozinho: com os segredos de Codespace do repositório
   (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `DATASET_S3_URI`), com os dados do desafio (a
   primeira carga leva alguns minutos); sem eles, com a fixture sintética.
2. **Entrar:** o script deixa a porta 8080 visível só para membros da organização e imprime o
   endereço. Cada pessoa abre o endereço logada no próprio GitHub (quem não é da organização não
   entra). Se a visibilidade não mudar sozinha: aba *Portas* > 8080 > *Visibilidade* > *Organização*.
3. **Conversar e avaliar:** escolha um cliente, converse, e no fim preencha *Avaliar esta conversa*:
   quem está testando, nota de 1 a 5, se o assistente resolveu e o que deu errado ou como deveria
   ter sido. A review fica no banco e vira Issue com a etiqueta `review-teste`.
4. **Sem permissão de Issue:** se o token do Codespace não puder criar Issues, a review fica só no
   banco; com um token que possa (segredo `REVIEWS_GITHUB_TOKEN`, ou `GITHUB_TOKEN=… make
   exportar-reviews`), as pendentes são publicadas.

Quem pode avaliar é `TESTADORES` no `compose.yaml`. O Codespace desliga sozinho depois de um tempo
sem uso; para testar de novo, é só ligá-lo (os dados e as reviews continuam no volume do banco).

## Recarga dos dados

Quando a versão dos dados (`data/manifesto/`) ou o código do pipeline mudam, o `make up` recarrega
tudo numa transação só. Durante a recarga a API responde 503 na hora, com `Retry-After`, e a
readiness diz `reloading`. Nada espera nem mistura as duas versões. No fim da mesma transação, o
atendimento montado com os dados anteriores não atravessa a troca: as conversas em andamento ficam
encerradas (a tela oferece uma nova), as propostas de pré-caso pendentes vencem e as sessões caem
(volte ao acesso de teste). Conversas com atendente, encaminhamentos e pré-casos continuam como
registro. Mesma versão já carregada: nada muda.

## Leitor de intenção (e5)

A API da demonstração lê em cascata: as regras leem primeiro, e só as frases que elas não entendem
vão para o leitor e5, um classificador que roda na CPU da própria API (~15–90 ms por mensagem,
nenhuma chamada de rede). Ele só classifica: vira intenção e status pelo mapeamento abaixo, e só com
confiança calibrada de 0,8 ou mais (`LEITOR_LIMITE`); abaixo disso a frase segue como não entendida
e a conversa pede de novo. Sim/não, fraude por palavra, pedido de atendente, valor, data, comércio
e identificadores continuam com as regras, e a política decide o que fazer. A API pede a carga do
leitor ao iniciar (log `leitor pronto` ou `leitor indisponivel`); qualquer falha segue pelas regras,
e o trace do turno (`app.eventos.interpretacao`, `make metricas`) diz quem leu cada mensagem:
`regras`, `leitor:e5@<versão>` ou `regras (leitor abaixo do limite)`.

- Modelo: `intfloat/multilingual-e5-base` (MIT) para transformar a frase em vetor + regressão
  logística nos fluxos, com a confiança calibrada por temperatura. Fluxo → leitura:
  `explicar_recusa`, `explicar_pendencia`, `explicar_estorno` → consultar com Declined, Pending,
  Reversed; `ver_transacoes` → consultar; `abrir_disputa` → contestar; `relato_de_fraude` → fraude;
  `fora_de_escopo`.
- Dados (todos CC-BY-4.0, fixados por commit e sha256 em `backend/src/jeje/leitor/corpus.py`):
  BANKING77 (PolyAI) em inglês e as traduções revisadas `c2d-usp/banking77-es-la` e
  `c2d-usp/banking77-pt-br`; MInDS-14 (PolyAI, fala real transcrita, es-ES e pt-PT) só no treino,
  para as categorias que o BANKING77 não tem (problema com o cartão, bloqueio, ver transações). A
  base do desafio não serve de gabarito: 42 textos distintos em 171 mil transcrições.
- Treino no estágio `modelo` da imagem (`python -m jeje.leitor treinar`); a versão é o hash das
  entradas (dados, pesos, mapeamento, parâmetros). Teste do BANKING77 (9.240 frases, nunca vistas
  no treino): acurácia 0,889 (en), 0,889 (es), 0,873 (pt); com confiança ≥ 0,8, 78% das frases, 96%
  de acerto. Mac e Docker dão a mesma versão, com alguns décimos de diferença na acurácia (ponto
  flutuante do torch).
- `make avaliar-leitor` (fora do gate, ~1,5 min, sem banco), no teste do BANKING77 em es e pt
  (6.160 frases), por mensagem: só as regras entendem certo 14% e pedem de novo 67–68%; com o
  leitor a 0,8, certo 63–66%, pedem de novo 13–18%, errado 18–19% (16–18% só com as regras) e
  fora de escopo lido como contestação ou fraude 0,6–0,9%. Mostra também os limites 0,7 e 0,9.
- Medido no protótipo do time (conversas simuladas com a `conversa.py` real e 80 clientes da base):
  sucesso 0,81 só com regras e 0,965 com o leitor em cascata. Fala real (MInDS-14, testado na língua
  que ficou fora do treino): pedidos fora de escopo que viram disputa ou fraude 0–0,8% (4,4% no
  pt-PT), contra 5–6% de um TF-IDF só com BANKING77.
- Limites: quando as regras acham que entenderam, o leitor nem é chamado, e 11–24% das frases dos
  conjuntos de teste terminam no fluxo errado por isso (ex.: "me cobraron dos veces" lido como
  consulta). O BANKING77 é traduzido e o MInDS-14 é ibérico: gíria latino-americana ("me la
  rebotaron", "pix") fica abaixo do limite e cai no esclarecimento. A avaliação que vale é um
  conjunto ES/PT escrito pelo time.
- Sem leitor: `INTERPRETADOR: "regras"` no serviço `api` do `compose.yaml`. Testes, fixture, CI e
  mutantes já rodam com regras (`compose.ci.yaml`); os testes do leitor usam um codificador falso
  (a imagem de testes não tem torch).

### Modelo local (Ollama, opcional)

`INTERPRETADOR: "ollama"` troca o leitor por um modelo local (Ollama do host, `qwen2.5:7b`) no
mesmo papel: só classifica o que as regras não entendem, e diz a língua, a intenção e o status
citado. Quando é chamado, pode ler fraude ou pedido de atendente (o turno encaminha), mas nunca
confirma nem escolhe transação, e a política decide o que fazer. Cumprimento e agradecimento não
viram pedido de atendente, e perguntar pelo estorno é consulta, não contestação (ACH-102). A API
pede a carga do modelo ao iniciar (log `modelo pronto` ou `modelo indisponivel`) e o mantém
carregado (`OLLAMA_KEEP_ALIVE`); qualquer falha — modelo fora do ar, lento, resposta fora do
formato — segue pelas regras, e o trace do turno diz quanto o modelo custou (~0,7 s por turno).

- O Ollama do host continua escutando só em `127.0.0.1`. A ponte `ollama-ponte` (profile `modelo`)
  escuta só no IP do host na rede do Docker (172.17.0.1) e repassa: nada fica exposto na rede e o
  Ollama não é reconfigurado.
- `make testar-modelo`: integração real com o Ollama (fora do gate; precisa da stack no ar).

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
  exceção (o banco repete valores nela).

### Auditoria

Todo efeito deixa um evento em `app.eventos`, na mesma transação do efeito, com o mesmo id da
requisição (`requisicao`): turno da conversa (regra, ação, efeito, fontes, quem leu a mensagem e o uso
do modelo), erro de turno desfeito (só a classe), ação fora da conversa (proposta e pré-caso pelo
painel, atendente que assume) e a própria recarga dos dados (quantas conversas, propostas e sessões
ela encerrou). Do `X-Request-ID` de uma resposta chega-se às linhas do log, ao evento e, pelo efeito,
ao turno (`app.turnos`), ao pré-caso (`app.pre_casos`) ou ao encaminhamento (`app.handoffs`).
`make metricas` recomputa tudo dos eventos; os pré-casos contados batem com os gravados.

### Limites de tempo e respostas de falha

Tudo no `compose.yaml`. Nenhuma requisição fica pendurada: ou responde, ou falha rápido com uma
resposta que diz o que fazer.

| Situação | Limite | Resposta |
| --- | --- | --- |
| Banco fora do ar ou sem responder | conexão em 3 s (`DB_CONNECT_TIMEOUT_S`) | 503 com `Retry-After: 5` |
| Todas as conexões do pool ocupadas | espera de 5 s (`DB_POOL_*`: 5 + 10 excedentes) | 503 com `Retry-After: 5` |
| Comando SQL da API demorado | 5 s por comando (`DB_STATEMENT_TIMEOUT_MS`) | 503 com `Retry-After: 5` |
| Recarga dos dados em andamento | nenhuma espera | 503 com `Retry-After: 30` |
| Modelo lento, fora do ar ou resposta estranha | 10 s por chamada (`OLLAMA_TIMEOUT_S`) | segue pelas regras, motivo no trace |
| Erro inesperado | — | 500 com o id da requisição |

## Testar

```bash
make check          # segredos + lint + testes + mutantes (cada teste precisa pegar um defeito real)
make e2e            # jornadas no navegador (Chromium e Firefox) contra a stack no ar
make gate           # check + e2e + mutantes de ponta a ponta
make metricas       # métricas recomputadas dos eventos de cada turno
make avaliar-leitor # leitor por mensagem no teste do BANKING77 es/pt: regras vs cascata (sem banco)
make testar-modelo  # integração real com o Ollama pela ponte (fora do gate)
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

## Operação e limites

- Política **simulada** e rotulada, com limites decididos pelo time (todos no `compose.yaml`): o
  assistente registra sozinho a contestação de transação aprovada até USD 5.000; à noite
  (20h–6h) pelo app ou pela web, até USD 1.000 por transação e 1.000 somados no dia (a base não
  diz se o aparelho é cadastrado, então todo acesso digital noturno conta como não cadastrado);
  transferência acima de USD 50.000 vai para análise de segurança. O resto vai para humano.
- Pré-caso é pedido de revisão: não move dinheiro nem promete prazo ou resultado.
- Motivo de recusa usa o significado genérico dos códigos ISO 8583, rotulado como tal.
- Acesso por cliente de demonstração (sem senha) e console do atendente existem só com
  `MODO_DEMO` ligado; num banco real, os dois exigiriam autenticação.
- Versão dos dados: o hash dos manifestos e o do código do pipeline ficam em `meta.dataset_version`
  (mostrados na página de status); mudou qualquer um, o `make up` recarrega (ver Recarga dos dados).
- Retenção: conversas, turnos, eventos, pré-casos e encaminhamentos ficam no banco sem expiração
  automática (demonstração); sessões valem 60 min e caem na recarga; propostas vencem em 10 min.
  Um banco real precisaria de prazo de retenção definido.
- Minimização: o leitor (e o modelo local) recebe só a mensagem, nunca cliente, transação ou sessão; os logs não
  guardam mensagem, token nem cliente; o encaminhamento leva o pedido cortado em 280 caracteres e só
  fatos verificados da transação.
- Capacidade medida neste PC (uma API, dados reais): turno lido pelas regras ~10 ms; leitura pelo
  leitor e5 36–91 ms (fixture, Mac M4 via Docker); com o modelo local carregado ~0,7 s; EDA inteira
  ~1 s; consulta por cliente abaixo de 1 ms; recarga completa ~5 min. Não medido: muitos clientes
  ao mesmo tempo e o servidor de publicação.
- Falta: publicação (destino por decidir), um conjunto de teste ES/PT escrito pelo time (com
  gíria) para medir o leitor, e a validação independente em andamento.
