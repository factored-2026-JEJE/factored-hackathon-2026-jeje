# Atalhos. Tudo roda via Docker Compose: o host precisa apenas de Docker (e make, opcional).
# Configuração não secreta vive no compose.yaml; segredos só no .env (ENG-003).

# Projeto compose dos testes; execuções paralelas usam outro nome: make check PROJETO_TESTE=x
PROJETO_TESTE ?= jeje-test
TESTE := docker compose -p $(PROJETO_TESTE) --profile test
# Roda um serviço de teste e sempre derruba o projeto de testes (banco efêmero incluso).
rodar_teste = $(TESTE) run --rm $(1); status=$$?; $(TESTE) down -v >/dev/null 2>&1; exit $$status

.PHONY: up up-fixture demo demo-down down reset segredos logs build lint test test-backend test-web mutantes e2e mutantes-e2e \
	metricas exportar-reviews avaliar-leitor calibrar-transacao contrato contrato-explorar testar-modelo check gate repro \
	e2e-pelo-portao publicar publicacao-down voltar limpar demo-limpar atacar test-avaliacao avaliar

up: ## Sobe a stack completa (dados reais do S3; precisa do .env) com a ponte do modelo: http://localhost:8080
	docker compose --profile modelo up -d --build --wait

up-fixture: ## Sobe a stack com a fixture sintética (sem .env, sem download)
	docker compose -f compose.yaml -f compose.ci.yaml up -d --build --wait

# Demonstração para o time: stack própria (jeje-demo) com a fixture e o leitor, publicada por um
# quick tunnel do cloudflared (grátis, sem conta; o endereço muda a cada vez que o túnel sobe).
DEMO := docker compose -p jeje-demo -f compose.yaml -f compose.demo.yaml
DEMO_PORTA ?= 8082

demo: ## Sobe a demonstração e abre o túnel (precisa do cloudflared); o endereço sai no log do túnel
	DEMO_PORTA=$(DEMO_PORTA) $(DEMO) up -d --build --wait
	cloudflared tunnel --no-autoupdate --url http://localhost:$(DEMO_PORTA)

demo-down: ## Para a demonstração (mantém o banco e as reviews)
	$(DEMO) down

# Limpeza dos dados de teste (ACH-040): sai o estado do canal (conversas, pré-casos, encaminhamentos,
# bloqueios, sessões e eventos), sem recarregar a base; ficam as personas e as reviews do time.
limpar: ## Apaga os dados de teste da stack do make up (a API responde 503 enquanto limpa)
	docker compose exec -T api python -m jeje.limpeza

demo-limpar: ## O mesmo na demonstração do time (make demo)
	$(DEMO) exec -T api python -m jeje.limpeza

# Publicação para os jurados (PRD-009): o main limpo, com o gate (CI no build) e as jornadas pelo
# portão verdes, sobe na stack jeje-pub (dados reais, senha obrigatória, sem portas no host) e sai
# pelo túnel nomeado do Cloudflare. Senha e token do túnel só no .env. A ponte do Ollama (a do LLM do
# "não entendi", no projeto jeje) fica de pé junto e volta sozinha depois de um reinício.
PUB := docker compose -p jeje-pub -f compose.yaml -f compose.publicacao.yaml
PORTAO := docker compose -p jeje-portao -f compose.yaml -f compose.ci.yaml -f mutantes/compose.mutantes.yaml -f compose.acesso.yaml

e2e-pelo-portao: ## Jornadas no navegador numa stack isolada (fixture) com o portão ligado (senha de teste)
	@export MUTANTE_TAG=portao; $(PORTAO) up -d --build --wait web && \
	$(PORTAO) --profile e2e run --rm --build e2e; status=$$?; \
	$(PORTAO) --profile e2e down -v --remove-orphans >/dev/null 2>&1; exit $$status

publicar: ## Publica o main para os jurados: gate, jornadas pelo portão, stack jeje-pub, a ponte do LLM e conferência
	@test -z "$$(git status --porcelain)" || { echo "publicar: a árvore tem mudanças"; exit 1; }
	@git fetch -q origin && test "$$(git rev-parse HEAD)" = "$$(git rev-parse origin/main)" || \
		{ echo "publicar: o HEAD não é o origin/main"; exit 1; }
	$(MAKE) segredos lint test
	$(MAKE) e2e-pelo-portao
	JEJE_TAG=$$(git rev-parse --short=12 HEAD) $(PUB) up -d --build --wait
	docker compose --profile modelo up -d ollama-ponte
	scripts/conferir-publicacao.sh

voltar: ## Volta a publicação ao COMMIT, já publicado antes: desce as migrations novas e sobe as imagens dele (ACH-116)
	@test -n "$(COMMIT)" || { echo "uso: make voltar COMMIT=<sha>"; exit 1; }
	PUB="$(PUB)" scripts/voltar.sh $(COMMIT)
	scripts/conferir-publicacao.sh

publicacao-down: ## Tira a publicação do ar (mantém o banco)
	$(PUB) down

down: ## Para a stack (mantém o banco)
	docker compose --profile modelo down

reset: ## Apaga o banco local (mantém os CSV baixados) para recarregar do zero
	docker compose --profile modelo down
	@# Volume do projeto efetivo (respeita -p/COMPOSE_PROJECT_NAME); só a linha do nome é lida.
	docker volume rm -f "$$(docker compose config | sed -n 's/^name: //p')_pgdata"

logs:
	docker compose logs -f

build: ## Constrói as imagens de teste
	$(TESTE) build test web-test

lint: build
	@$(call rodar_teste,lint)

test-backend: build
	@$(call rodar_teste,test)

test-web: build
	@$(call rodar_teste,web-test)

# Os testes do oráculo da avaliação (avaliacao/tests, NOV-13a): só a biblioteca padrão do Python.
PYTHON_AVALIACAO := python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
test-avaliacao: ## Os testes do oráculo do atacante (avaliacao/tests), sem a stack
	docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -v "$$PWD":/repo:ro -w /repo $(PYTHON_AVALIACAO) \
		python -m unittest discover -s avaliacao/tests -t .

test: test-backend test-web test-avaliacao

mutantes: build ## Prova que cada teste derruba seu mutante (backend e web)
	@$(call rodar_teste,mutantes)
	@$(call rodar_teste,mutantes-web)

e2e: up ## Jornadas no navegador contra a stack em execução
	docker compose --profile e2e run --rm --build e2e

mutantes-e2e: ## Mutantes E2E: uma stack isolada por mutante
	docker compose --profile mutantes-e2e run --rm --build mutantes-e2e

exportar-reviews: ## Publica como Issue as reviews de teste que ficaram só no banco (precisa de GITHUB_TOKEN)
	docker compose exec -e GITHUB_TOKEN api python -m jeje.reviews

metricas: ## Métricas do atendimento recomputadas dos eventos da stack em execução
	docker compose exec -T api python -m jeje.metricas

avaliar-leitor: ## Leitura por mensagem no teste do BANKING77 es/pt: regras, e5 e TF-IDF (sem banco); fora do gate
	docker compose build migrate
	docker compose run --rm --no-deps api python -m jeje.avaliacao_leitor

calibrar-transacao: ## "Qual transação" (DEV-037): recalibra o ranking com a base da stack no ar (make up) e grava backend/src/jeje/qual_transacao.json, só com agregados
	docker compose build migrate
	docker compose run --rm --no-deps --user "$$(id -u):$$(id -g)" -v "$$PWD/backend/src/jeje:/saida" \
		api python -m jeje.calibrar_qual_transacao /saida/qual_transacao.json

testar-modelo: build ## Integração real com o Ollama pela ponte (precisa de make up); fora do gate
	@$(call rodar_teste,test pytest -q -p no:cacheprovider -m ollama tests/test_modelo_real.py)

contrato-explorar: build ## Exploração aleatória do contrato (fora do gate); achado vira teste de regressão
	@$(call rodar_teste,test pytest -q -p no:cacheprovider -m exploracao tests/test_contrato.py)

contrato: build ## Regenera o OpenAPI versionado e os tipos TypeScript
	$(TESTE) run --rm --no-deps -T test python -m jeje.contrato > contrato/openapi.json
	$(TESTE) build web-test
	$(TESTE) run --rm --no-deps -T web-test node scripts/gerar-tipos.ts /contrato/openapi.json /dev/stdout > frontend/src/api/schema.d.ts

segredos: ## Nenhuma chave nem valor do .env no histórico Git (gitleaks + busca dos valores)
	./scripts/testar-verificar-segredos.sh
	./scripts/verificar-segredos.sh

check: segredos lint test mutantes ## Tudo que não precisa da stack no ar

# `e2e` sobe a stack com --wait: só roda com todos os serviços saudáveis (host precisa só de Docker).
gate: check e2e mutantes-e2e ## Portão de uma meta: checks, jornadas e mutantes E2E

# Reprodução do zero (o CI do projeto roda aqui, no build, sem GitHub; PRD-009).
COMMIT ?= HEAD
MODO ?= completo
repro: ## Do zero: clone limpo do COMMIT, stack isolada com a fixture, segredos e todos os gates
	scripts/repro.sh $(COMMIT) $(MODO)

# O portão de release com o atacante adaptativo (DEV-021b, NOV-13a). Fica fora do gate: precisa do
# Ollama com o qwen2.5:7b e o qwen3:4b, da ponte até ele e da GPU livre (de 30 a 45 min). O limite e
# os episódios ficam no compose.atacar.yaml; ARGS vai por cima (ex.: ARGS="--mecanismos M4 --episodios 2").
atacar: ## Stack isolada do commit (a variante entregue) e o atacante da validação: falha se os inseguros passam do limite
	scripts/atacar.sh $(ARGS)

# A avaliação verificável (2.11): os cenários de desenvolvimento e de validação, julgados pelo estado
# final no banco, numa stack isolada com a base de avaliação. VARIANTE=regras roda sem o LLM.
VARIANTE ?= leitor_modelo
avaliar: ## Os cenários de dev e de validação numa stack isolada do commit; a tabela em resultados/avaliacao/
	scripts/avaliar.sh $(VARIANTE)
