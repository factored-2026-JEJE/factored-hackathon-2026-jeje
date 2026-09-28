#!/usr/bin/env bash
# Reprodução do zero (DEV-021): clone limpo do commit, stack isolada com a fixture versionada
# (sem chaves, sem portas no host), gates completos e remoção de tudo o que foi criado.
#
#   scripts/repro.sh [commit] [rapido]
#
# Só depende do que está versionado: o clone não tem `.env`, dados baixados nem arquivos locais.
# Projeto, tags e prefixos próprios não colidem com a stack de desenvolvimento em execução.
# `rapido` pula os mutantes (sobe, jornadas no navegador, lint e testes).
set -euo pipefail

origem=$(git rev-parse --show-toplevel)
commit=$(git -C "$origem" rev-parse --verify "${1:-HEAD}^{commit}")
modo=${2:-completo}
id="repro$(date +%s)"
area=$(mktemp -d)

export JEJE_TAG="$id" PROJETO_TESTE="$id-test" MUTANTES_PREFIXO="$id-mut"
stack=(docker compose -p "$id" -f compose.yaml -f compose.ci.yaml -f mutantes/compose.mutantes.yaml)

limpar() {
  status=$?
  if [ -d "$area/repo" ]; then
    (cd "$area/repo" && "${stack[@]}" --profile e2e down -v --remove-orphans >/dev/null 2>&1) || true
  fi
  imagens=$(docker images -q --filter "reference=*:$id" | sort -u)
  [ -z "$imagens" ] || docker rmi -f $imagens >/dev/null 2>&1 || true
  rm -rf "$area"
  echo "repro: $([ "$status" -eq 0 ] && echo ok || echo "FALHOU ($status)") em ${SECONDS}s ($commit)"
}
trap limpar EXIT

echo "repro: clone limpo de $commit em $area"
git clone -q --no-hardlinks "$origem" "$area/repo"
cd "$area/repo"
git checkout -q --detach "$commit"
test -z "$(git status --porcelain --ignored)" || { echo "repro: clone não está limpo" >&2; exit 1; }
test ! -e .env || { echo "repro: .env não pode existir no clone" >&2; exit 1; }

echo "repro: stack com a fixture (projeto $id)"
"${stack[@]}" up -d --build --wait web
"${stack[@]}" --profile e2e run --rm --build e2e

if [ "$modo" = rapido ]; then
  make lint test
else
  make lint test mutantes mutantes-e2e
fi
