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
  lidos=$(mktemp)
  trap 'rm -f "$valores" "$lidos"' EXIT
  chaves=$(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' .env.example | paste -sd'|' -)
  # Valores exatamente como o Compose os lê do .env (aspas, export, espaços, comentário, CRLF,
  # BOM: DEV-020e), num ambiente limpo para variáveis do shell não mascararem o arquivo.
  env -i PATH="$PATH" HOME="$HOME" docker compose config --environment 2>/dev/null \
    | grep -E "^($chaves)=" | cut -d= -f2- > "$lidos" || true
  # Também o nome do bucket isolado. Vazios ou com menos de 8 caracteres não são segredo e,
  # numa lista de padrões, casariam com qualquer linha (DEV-020d).
  { cat "$lidos"; sed -n 's|^s3://\([^/]*\).*|\1|p' "$lidos"; } | grep -E '^.{8,}$' > "$valores" || true
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
