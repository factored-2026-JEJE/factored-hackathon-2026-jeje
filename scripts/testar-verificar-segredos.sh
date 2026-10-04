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
  # O script lê o .env pelo parser do Compose: basta um compose.yaml mínimo.
  printf 'services:\n  x:\n    image: alpine\n' > "$d/compose.yaml"
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

# DEV-020e: toda sintaxe que o Compose aceita no .env (valor lido é "segredo-falso-2026-abc").
SEGREDO=segredo-falso-2026-abc
i=0
for linha in \
  "AWS_SECRET_ACCESS_KEY=$SEGREDO" \
  "AWS_SECRET_ACCESS_KEY=\"$SEGREDO\"" \
  "AWS_SECRET_ACCESS_KEY='$SEGREDO'" \
  "AWS_SECRET_ACCESS_KEY=$SEGREDO # comentario" \
  "export AWS_SECRET_ACCESS_KEY=$SEGREDO" \
  "AWS_SECRET_ACCESS_KEY= $SEGREDO" \
  "AWS_SECRET_ACCESS_KEY = $SEGREDO" \
  "AWS_SECRET_ACCESS_KEY=$SEGREDO\r" \
  "\357\273\277AWS_SECRET_ACCESS_KEY=$SEGREDO"; do
  i=$((i + 1))
  d=$(repo "sintaxe_$i"); printf "$linha\n" > "$d/.env"
  caso "sintaxe $i sem vazamento passa" 0 "$d"
  printf 'valor: %s\n' "$SEGREDO" > "$d/vazou.txt"
  caso "sintaxe $i com valor em arquivo não rastreado falha" 1 "$d"
done
for i in 2 5 8; do
  d="$tmp/sintaxe_$i"
  git -C "$d" add vazou.txt && git -C "$d" -c user.name=t -c user.email=t@t commit -qm vazou
  caso "sintaxe $i com valor no histórico falha" 1 "$d"
done

# ACH-291: o gitleaks também numa worktree, cujo .git aponta para fora da pasta. Sem .env, só ele
# procura: um token do GitHub (falso) no histórico tem de ser achado nas duas pastas. O token é
# montado aqui, em duas partes, para este arquivo não virar ele mesmo um vazamento no histórico.
TOKEN="gh""p_7Hq2Lx9VbN4mR8tY3kWp6sZd1FgJ5cQa0EuI"
d=$(repo gitleaks_principal)
printf 'token = "%s"\n' "$TOKEN" > "$d/config.txt"
git -C "$d" add config.txt && git -C "$d" -c user.name=t -c user.email=t@t commit -qm token
caso "token no histórico, sem .env, falha (o gitleaks lê o histórico)" 1 "$d"
d=$(repo gitleaks_limpo)
git -C "$d" worktree add -q "$tmp/worktree_limpa" 2>/dev/null
cp "$d/scripts/verificar-segredos.sh" "$tmp/worktree_limpa/scripts/" 2>/dev/null || true
caso "worktree sem segredo passa (o histórico abre no container)" 0 "$tmp/worktree_limpa"
git -C "$tmp/gitleaks_principal" worktree add -q "$tmp/worktree_com_chave" 2>/dev/null
caso "token no histórico de uma worktree falha" 1 "$tmp/worktree_com_chave"

[ "$falhas" -eq 0 ] || exit 1
