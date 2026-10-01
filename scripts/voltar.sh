#!/usr/bin/env bash
# Volta a publicação a um commit já publicado antes (ACH-116). As imagens antigas não conhecem as
# migrations novas: com elas, o migrate falha ("Can't locate revision") e a API não sobe. Então a
# imagem de agora, que conhece todas, desce o banco até o head do commit antigo, e só depois as
# imagens dele sobem.
#
# Uso: scripts/voltar.sh <commit>   (PUB: o compose da publicação, como no Makefile)
set -euo pipefail
COMMIT=${1:?uso: scripts/voltar.sh <commit>}
PUB=${PUB:-"docker compose -p jeje-pub -f compose.yaml -f compose.publicacao.yaml"}
ALVO=$(git rev-parse --short=12 "$COMMIT")
docker image inspect "jeje-api:$ALVO" > /dev/null 2>&1 ||
  { echo "voltar: não há a imagem jeje-api:$ALVO (o commit foi publicado nesta máquina?)"; exit 1; }
API=$($PUB ps -q api)
test -n "$API" || { echo "voltar: a API da publicação não está no ar"; exit 1; }
ATUAL=$(docker inspect --format '{{.Config.Image}}' "$API" | sed 's/^jeje-api://')
HEAD_ALVO=$(docker run --rm --entrypoint alembic "jeje-api:$ALVO" heads | awk '{print $1}')
echo "voltar: de $ATUAL para $ALVO (migration $HEAD_ALVO)"
JEJE_TAG=$ATUAL $PUB run --rm --no-deps migrate alembic downgrade "$HEAD_ALVO"
JEJE_TAG=$ALVO $PUB up -d --wait
