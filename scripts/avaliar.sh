#!/bin/bash
# A avaliação verificável (make avaliar, 2.11): os cenários de desenvolvimento e de validação
# (avaliacao/cenarios.json, escritos pela validação) contra uma stack isolada do commit. A base é a
# de avaliação (a fixture mais 24 clientes sintéticos), carregada pelo seed com 40 personas, e cada
# cenário é julgado pelo estado final no banco (avaliacao/avaliador.py). A tabela fica em
# resultados/avaliacao/avaliacao-<commit>.json, para o site, e .md, para o README. O conjunto final do
# teste (VAL-019) não está aqui: ele roda uma vez, na versão congelada.
#
# Nunca roda contra a publicação: o alvo é o web da stack isolada, e o avaliador recusa qualquer
# outro.
#
#   scripts/avaliar.sh [regras|leitor|leitor_modelo]   (padrão: leitor_modelo, a variante entregue)
#
# A leitor_modelo precisa do Ollama do host com o qwen3:4b, pela ponte (a ollama-ponte do perfil
# "modelo"), e falha (2) se nenhum turno chegar ao LLM. Com a GPU, os 100 cenários levam uns 15 min.
# Saída: 0 rodou (a tabela diz os números), 2 a stack, o Ollama ou o LLM fora.
set -u
cd "$(dirname "$0")/.."
variante="${1:-leitor_modelo}"
commit=$(git rev-parse HEAD)
curto=${commit:0:12}
[ -n "$(git status --porcelain)" ] && curto="$curto-sujo"
projeto="jeje-avaliar-${curto}"
export MUTANTE_TAG="avaliar-${curto}"
export AVALIAR_VARIANTE="$variante"
export AVALIAR_BASE="$PWD/resultados/avaliacao/base-${curto}"
P=(docker compose -p "$projeto" -f compose.yaml -f compose.ci.yaml -f mutantes/compose.mutantes.yaml -f compose.avaliar.yaml)
mkdir -p resultados/avaliacao
trap '"${P[@]}" --profile avaliar down -v --remove-orphans >/dev/null 2>&1
docker image rm "jeje-mut-api:$MUTANTE_TAG" "jeje-mut-web:$MUTANTE_TAG" >/dev/null 2>&1' EXIT

if [ "$variante" = leitor_modelo ] && ! docker run --rm --add-host host.docker.internal:host-gateway python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea \
  python -c "
import json, sys, urllib.request
modelos = {m['name'] for m in json.load(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5))['models']}
sys.exit(0 if 'qwen3:4b' in modelos else 'falta o qwen3:4b no Ollama')
" >&2; then
  echo "avaliar: o Ollama não responde em host.docker.internal:11434 com o qwen3:4b (a ponte: docker compose --profile modelo up -d ollama-ponte)" >&2
  exit 2
fi
U=(--user "$(id -u):$(id -g)")
# A base: gerada pelo pacote da validação a partir da fixture do commit, com o manifesto regenerado
# pelo próprio produto.
# A imagem da API sai do serviço migrate (o api, o seed e o avaliador usam a mesma).
"${P[@]}" build migrate web || exit 2
"${P[@]}" --profile avaliar run --rm --no-deps "${U[@]}" avaliador base --produto /produto --destino "/saida/base-${curto}" || exit 2
"${P[@]}" run --rm --no-deps "${U[@]}" seed python -m jeje.dados manifesto || exit 2
# A stack com a base carregada, e os cenários na variante.
"${P[@]}" up -d --wait web || exit 2
extra=()
[ "$variante" = leitor_modelo ] && extra=(--exigir-llm)
"${P[@]}" --profile avaliar run --rm "${U[@]}" avaliador rodar --url http://web:8080/api \
  --base "/saida/base-${curto}" --produto /produto --variante "$variante" --commit "$commit" \
  --banco-url postgresql://jeje:jeje@db:5432/jeje --saida /saida "${extra[@]}"
rodou=$?
[ "$rodou" -eq 0 ] || exit "$rodou"
"${P[@]}" --profile avaliar run --rm --no-deps "${U[@]}" avaliador tabela \
  "/saida/avaliacao-${commit:0:12}-${variante}-1.json" --saida /saida
