# Atalhos. Tudo roda via Docker Compose: o host precisa apenas de Docker (e make, opcional).
# Configuração não secreta vive no compose.yaml; segredos só no .env (ENG-003).

# Projeto compose dos testes; execuções paralelas usam outro nome: make check PROJETO_TESTE=x
PROJETO_TESTE ?= jeje-test
TESTE := docker compose -p $(PROJETO_TESTE) --profile test
# Roda um serviço de teste e sempre derruba o projeto de testes (banco efêmero incluso).
rodar_teste = $(TESTE) run --rm $(1); status=$$?; $(TESTE) down -v >/dev/null 2>&1; exit $$status

.PHONY: up up-fixture down reset segredos logs build lint test test-backend test-web mutantes e2e mutantes-e2e \
	metricas avaliar-leitor contrato contrato-explorar testar-modelo check gate

up: ## Sobe a stack completa (dados reais do S3; precisa do .env) com a ponte do modelo: http://localhost:8080
	docker compose --profile modelo up -d --build --wait

up-fixture: ## Sobe a stack com a fixture sintética (sem .env, sem download)
	docker compose -f compose.yaml -f compose.ci.yaml up -d --build --wait

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

test: test-backend test-web

mutantes: build ## Prova que cada teste derruba seu mutante (backend e web)
	@$(call rodar_teste,mutantes)
	@$(call rodar_teste,mutantes-web)

e2e: up ## Jornadas no navegador contra a stack em execução
	docker compose --profile e2e run --rm --build e2e

mutantes-e2e: ## Mutantes E2E: uma stack isolada por mutante
	docker compose --profile mutantes-e2e run --rm --build mutantes-e2e

metricas: ## Métricas do atendimento recomputadas dos eventos da stack em execução
	docker compose exec -T api python -m jeje.metricas

avaliar-leitor: ## Leitor por mensagem no teste do BANKING77 es/pt: regras vs cascata (sem banco); fora do gate
	docker compose build migrate
	docker compose run --rm --no-deps api python -m jeje.avaliacao_leitor

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
