#!/usr/bin/env bash
# Sobe a demonstração no Codespace: dados do desafio se os segredos existem, senão a fixture;
# deixa o site (porta 8080) visível para a organização e passa à API o token das Issues de review.
set -euo pipefail
cd "$(dirname "$0")/.."

until docker info >/dev/null 2>&1; do sleep 1; done

# Token das Issues: um próprio (segredo REVIEWS_GITHUB_TOKEN) ou o do Codespace. Sem nenhum que
# funcione, as reviews ficam só no banco (e `make exportar-reviews` as publica depois).
export GITHUB_TOKEN="${REVIEWS_GITHUB_TOKEN:-${GITHUB_TOKEN:-}}"

if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" && -n "${DATASET_S3_URI:-}" ]]; then
  umask 077
  printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\nDATASET_S3_URI=%s\n' \
    "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" "$DATASET_S3_URI" > .env
  echo "Subindo com os dados do desafio (primeira vez: download e carga levam alguns minutos)."
  docker compose up -d --build --wait db migrate seed api web
else
  echo "Sem os segredos do S3: subindo com a fixture sintética."
  docker compose -f compose.yaml -f compose.ci.yaml up -d --build --wait
fi

# Site visível só para membros da organização (cada um entra com o próprio GitHub).
if ! gh codespace ports visibility 8080:org -c "$CODESPACE_NAME" 2>/dev/null; then
  echo "Não consegui mudar a visibilidade da porta: na aba Portas, clique com o botão direito"
  echo "na 8080 > Visibilidade da porta > Organização."
fi
echo "Pronto: https://${CODESPACE_NAME}-8080.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
