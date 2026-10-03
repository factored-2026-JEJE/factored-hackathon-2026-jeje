#!/bin/sh
# Barra segredos no Git (ENG-003): gitleaks no histórico inteiro e, havendo .env, busca dos seus
# valores (inclusive o nome do bucket isolado) no histórico e nos arquivos não ignorados.
# Nunca imprime os valores procurados.
set -eu
cd "$(dirname "$0")/.."

GITLEAKS=zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
# Numa worktree, o .git é um arquivo que aponta para o repositório principal, fora desta pasta: o
# container recebe o diretório comum no mesmo caminho. Sem ele, o gitleaks não lê o histórico, loga o
# erro do git e sai 0 sem conferir nada (ACH-291). O dono dos arquivos não é o do container: o git
# precisa aceitar o diretório (safe.directory).
comum=$(git rev-parse --path-format=absolute --git-common-dir)
no_container() {
  docker run --rm -v "$PWD":/repo:ro -v "$comum":"$comum":ro \
    -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' "$@"
}
# O histórico tem de abrir de verdade no container; senão, falha (nunca um "ok" sem ter lido nada).
if ! no_container --entrypoint git "$GITLEAKS" -C /repo rev-parse -q --verify HEAD >/dev/null; then
  echo "ERRO: o histórico Git não abre no container do gitleaks" >&2
  exit 1
fi
no_container "$GITLEAKS" git /repo --no-banner --redact --log-level warn

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
