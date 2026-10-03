#!/bin/bash
# O portão de release com o atacante adaptativo (make atacar, DEV-021b, PRD-012): sobe uma stack
# isolada do commit (a fixture, o leitor e5, sem portas no host e sem o LLM do site), roda o
# atacante da validação (avaliacao/atacante.py, NOV-13a), que tenta em várias rodadas levar o
# atendimento a uma ação insegura, e falha quando os episódios inseguros passam do limite. O
# relatório fica em resultados/atacante/. Nunca contra a publicação: o alvo é o serviço web da
# stack isolada (o atacante recusa qualquer outro).
#
#   scripts/atacar.sh [argumentos do atacante]   (padrão: --rapido, 2 episódios por mecanismo e língua)
# Precisa do Ollama no host com o modelo do atacante (qwen2.5:7b) e da ponte até ele (a do
# make up). Saída: 0 passa, 1 o portão falha, 2 inconclusivo (Ollama ou API fora).
set -u
cd "$(dirname "$0")/.."
commit=$(git rev-parse --short=12 HEAD)
[ -n "$(git status --porcelain)" ] && commit="$commit-sujo"
projeto="jeje-atacar-${commit}"
export MUTANTE_TAG="atacar-${commit}"
P=(docker compose -p "$projeto" -f compose.yaml -f compose.ci.yaml -f mutantes/compose.mutantes.yaml -f compose.atacar.yaml)
argumentos=("$@")
[ ${#argumentos[@]} -eq 0 ] && argumentos=(--rapido)
mkdir -p resultados/atacante
trap '"${P[@]}" --profile atacar down -v --remove-orphans >/dev/null 2>&1' EXIT

# O Ollama do host, visto de um container: sem ele, o portão é inconclusivo, não verde.
if ! docker run --rm --add-host host.docker.internal:host-gateway python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea \
  python -c "import urllib.request; urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=5)" >/dev/null 2>&1; then
  echo "atacar: o Ollama não responde em host.docker.internal:11434 (suba a ponte: docker compose --profile modelo up -d ollama-ponte)" >&2
  exit 2
fi
"${P[@]}" up -d --build --wait web || exit 2
"${P[@]}" --profile atacar run --rm --user "$(id -u):$(id -g)" atacante python -m avaliacao.atacante \
  --url http://web:8080/api --ollama http://host.docker.internal:11434 \
  --compose compose.yaml compose.ci.yaml compose.atacar.yaml \
  --commit "$commit" --saida /saida "${argumentos[@]}"
