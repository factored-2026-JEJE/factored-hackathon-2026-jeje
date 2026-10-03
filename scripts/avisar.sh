#!/bin/sh
# O aviso de que a publicação caiu (DEV-021a): a mensagem vai para o canal que Jader escolher, pelo
# endereço que fica só no .env (AVISO_URL, um segredo: o tópico do ntfy ou um webhook que aceite um
# POST de texto). Sem o endereço, a mensagem fica só no registro da vigia, e o script sai com 2.
#
#   scripts/avisar.sh "mensagem"
set -eu
cd "$(dirname "$0")/.."
mensagem=${1:?uso: scripts/avisar.sh "mensagem"}
endereco=$(sed -n 's/^AVISO_URL=//p' .env 2>/dev/null | tail -n 1 | sed "s/^[\"']//; s/[\"']\$//")
if [ -z "$endereco" ]; then
  echo "avisar: sem AVISO_URL no .env; a mensagem fica só no registro: $mensagem" >&2
  exit 2
fi
curl -fsS -m 20 -H "Title: JEJE · publicação" -d "$mensagem" "$endereco" >/dev/null
