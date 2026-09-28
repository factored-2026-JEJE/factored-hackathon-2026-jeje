#!/bin/sh
# Teste discriminante de verificar-segredos.sh em repositórios descartáveis: cada caso tem o
# código de saída esperado (0 = limpo, 1 = segredo encontrado). Valores são falsos.
set -u
raiz=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
falhas=0

repo() {
  d="$tmp/$1"
  mkdir -p "$d/scripts"
  cp "$raiz/scripts/verificar-segredos.sh" "$d/scripts/"
  cp "$raiz/.env.example" "$d/.env.example"
  printf '.env\n' > "$d/.gitignore"
  git -C "$d" init -q
  git -C "$d" add .
  git -C "$d" -c user.name=t -c user.email=t@t commit -qm base
  echo "$d"
}

caso() {
  nome=$1 esperado=$2 dir=$3
  (cd "$dir" && ./scripts/verificar-segredos.sh >/dev/null 2>&1)
  obtido=$?
  [ "$obtido" -ne 0 ] && obtido=1
  if [ "$obtido" = "$esperado" ]; then echo "ok    $nome"; else
    echo "FALHA $nome: esperado $esperado, obtido $obtido"
    falhas=$((falhas + 1))
  fi
}

CHAVES='AWS_ACCESS_KEY_ID=AKIAFALSOFALSO123456
AWS_SECRET_ACCESS_KEY=segredo-falso-de-teste-com-quarenta-caractere
DATASET_S3_URI=s3://bucket-falso-de-teste/data/'

d=$(repo vazio); cp "$d/.env.example" "$d/.env"
caso ".env do README com valores vazios passa" 0 "$d"

d=$(repo curtos); printf 'AWS_ACCESS_KEY_ID= \nDATASET_S3_URI=abc\n' > "$d/.env"
caso "valores curtos ou só espaço não viram padrão" 0 "$d"

d=$(repo limpo); printf '%s\n' "$CHAVES" > "$d/.env"
caso "chaves no .env e nada vazado passa" 0 "$d"

d=$(repo nao_rastreado); printf '%s\n' "$CHAVES" > "$d/.env"
printf 'minha chave: AKIAFALSOFALSO123456\n' > "$d/rascunho.md"
caso "chave em arquivo não rastreado falha" 1 "$d"

d=$(repo historico); printf '%s\n' "$CHAVES" > "$d/.env"
printf 'bucket: bucket-falso-de-teste\n' > "$d/notas.txt"
git -C "$d" add notas.txt && git -C "$d" -c user.name=t -c user.email=t@t commit -qm notas
caso "nome do bucket no histórico falha" 1 "$d"

[ "$falhas" -eq 0 ] || exit 1
