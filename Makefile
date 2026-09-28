# Atalhos. Tudo roda via Docker Compose: o host precisa apenas de Docker (e make, opcional).
# Configuração não secreta vive no compose.yaml; segredos só no .env (ENG-003).

TESTE := docker compose -p jeje-test --profile test
# Roda um serviço de teste e sempre derruba o projeto de testes (banco efêmero incluso).
rodar_teste = $(TESTE) run --rm $(1); status=$$?; $(TESTE) down -v >/dev/null 2>&1; exit $$status

.PHONY: up up-fixture down reset logs build lint test test-backend test-web mutantes e2e mutantes-e2e \
	contrato check gate

up: ## Sobe a stack completa (dados reais do S3; precisa do .env): http://localhost:8080
	docker compose up -d --build --wait

up-fixture: ## Sobe a stack com a fixture sintética (sem .env, sem download)
	docker compose -f compose.yaml -f compose.ci.yaml up -d --build --wait

down: ## Para a stack (mantém o banco)
	docker compose down

reset: ## Apaga o banco local (mantém os CSV baixados) para recarregar do zero
	docker compose down
	docker volume rm -f jeje_pgdata

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

contrato: build ## Regenera o OpenAPI versionado e os tipos TypeScript
	$(TESTE) run --rm --no-deps -T test python -m jeje.contrato > contrato/openapi.json
	$(TESTE) build web-test
	$(TESTE) run --rm --no-deps -T web-test node scripts/gerar-tipos.ts /contrato/openapi.json /dev/stdout > frontend/src/api/schema.d.ts

check: lint test mutantes ## Tudo que não precisa da stack no ar

gate: check e2e mutantes-e2e ## Portão de uma meta: checks, jornadas e mutantes E2E
	@curl -sf http://localhost:8080/api/health/ready >/dev/null && echo "readiness: pronto" \
		|| echo "readiness: indisponível (ver http://localhost:8080)"
