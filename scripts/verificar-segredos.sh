#!/bin/sh
# Barra segredos no Git (ENG-003): gitleaks no histórico inteiro e, havendo .env, busca dos seus
# valores (inclusive o nome do bucket isolado) no histórico e nos arquivos não ignorados.
# Nunca imprime os valores procurados.
set -eu
cd "$(dirname "$0")/.."

docker run --rm -v "$PWD":/repo:ro \
  zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
  git /repo --no-banner --redact --log-level warn

if [ -f .env ]; then
  valores=$(mktemp)
  trap 'rm -f "$valores"' EXIT
  # Valores com 8+ caracteres sem espaço (chaves, URI e o nome do bucket isolado). Vazios ou
  # curtos não são segredo e, numa lista de padrões, casariam com qualquer linha (DEV-020d).
  {
    sed -n 's/^[A-Z_][A-Z0-9_]*=[[:space:]]*\([^[:space:]]*\)[[:space:]]*$/\1/p' .env
    sed -n 's|^DATASET_S3_URI=[[:space:]]*s3://\([^/[:space:]]*\).*|\1|p' .env
  } | grep -E '^.{8,}$' > "$valores" || true
  if [ ! -s "$valores" ]; then
    echo "segredos: .env sem valores para procurar"
    echo "segredos: ok"
    exit 0
  fi
  if git log --all -p | grep -q -F -f "$valores"; then
    echo "ERRO: valor do .env aparece no histórico Git" >&2
    exit 1
  fi
  if git grep -q --untracked -F -f "$valores" -- . ':!.env'; then
    echo "ERRO: valor do .env aparece em arquivo não ignorado" >&2
    exit 1
  fi
  echo "segredos: nenhum valor do .env no histórico nem nos arquivos"
fi
echo "segredos: ok"
