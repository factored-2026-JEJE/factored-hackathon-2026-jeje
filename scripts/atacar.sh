#!/bin/bash
# O portão de release com o atacante adaptativo (make atacar, DEV-021b, PRD-012). Sobe uma stack
# isolada do commit, com a fixture e sem portas no host. A API é a variante entregue: o leitor e5 com
# o LLM local do "não entendi" e a garantia de fraude, sem o LLM do site. Nela roda o atacante da
# validação (avaliacao/atacante.py, NOV-13a), que tenta em várias rodadas levar o atendimento a uma
# ação insegura. O portão falha quando os episódios inseguros passam do limite, e é inconclusivo
# quando nenhum turno chega ao LLM do produto. O limite e os episódios ficam no compose.atacar.yaml
# (0 e 8 por mecanismo e língua, 128 episódios). O relatório fica em resultados/atacante/.
#
# Nunca roda contra a publicação: o alvo é o serviço web da stack isolada, e o atacante recusa
# qualquer outro.
#
#   scripts/atacar.sh [argumentos do atacante]   (ex.: --mecanismos M4 --episodios 2; o último vale)
#
# Precisa:
#   - do Ollama no host com o qwen2.5:7b (o atacante) e o qwen3:4b (o LLM do produto);
#   - da ponte até ele (a ollama-ponte do perfil "modelo");
#   - da GPU livre: os 128 episódios levam de 30 a 45 min.
# Saída: 0 passa, 1 o portão falha, 2 inconclusivo (Ollama, modelo ou API fora, ou o LLM não exercido).
set -u
cd "$(dirname "$0")/.."
commit=$(git rev-parse --short=12 HEAD)
[ -n "$(git status --porcelain)" ] && commit="$commit-sujo"
projeto="jeje-atacar-${commit}"
export MUTANTE_TAG="atacar-${commit}"
P=(docker compose -p "$projeto" -f compose.yaml -f compose.ci.yaml -f mutantes/compose.mutantes.yaml -f compose.atacar.yaml)
mkdir -p resultados/atacante
trap '"${P[@]}" --profile atacar down -v --remove-orphans >/dev/null 2>&1
docker image rm "jeje-mut-api:$MUTANTE_TAG" "jeje-mut-web:$MUTANTE_TAG" >/dev/null 2>&1' EXIT

# O Ollama do host, visto de um container, com os dois modelos: sem eles, o portão é inconclusivo,
# não verde.
if ! docker run --rm --add-host host.docker.internal:host-gateway python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea \
  python -c "
import json, sys, urllib.request
modelos = {m['name'] for m in json.load(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5))['models']}
faltam = {'qwen2.5:7b', 'qwen3:4b'} - modelos
sys.exit('faltam no Ollama: ' + ', '.join(sorted(faltam)) if faltam else 0)
" >&2; then
  echo "atacar: o Ollama não responde em host.docker.internal:11434 com o qwen2.5:7b e o qwen3:4b (a ponte: docker compose --profile modelo up -d ollama-ponte)" >&2
  exit 2
fi
"${P[@]}" up -d --build --wait web || exit 2
"${P[@]}" --profile atacar run --rm --user "$(id -u):$(id -g)" atacante --commit "$commit" "$@"
