#!/usr/bin/env bash
# Conferência da publicação para os jurados (PRD-009), pelo endereço público: sem o cookie de acesso,
# a API recusa; a senha errada não entra; a certa entra, com o cookie seguro. Nunca mostra a senha
# nem o cookie: só o nome de cada conferência e o resultado.
#
#   scripts/conferir-publicacao.sh [--conversa] [endereço]   (padrão: PUBLICACAO_URL ou https://jeje.jaderlouis.com.br)
#
# Com --conversa (o teste diário da publicação de pé, DEV-021a), também uma conversa de verdade em
# cada língua: uma persona, uma conversa e um turno sem efeito ("por que recusaram minha compra?"),
# conferindo a resposta na língua da conversa e com a regra que decidiu. Cada rodada deixa uma
# sessão e duas conversas de consulta no banco da publicação: nenhum pré-caso, bloqueio ou caso.
set -euo pipefail

conversa=0
if [ "${1:-}" = "--conversa" ]; then
  conversa=1
  shift
fi
url=${1:-${PUBLICACAO_URL:-https://jeje.jaderlouis.com.br}}
raiz=$(git rev-parse --show-toplevel)
# A senha sai do compose da publicação, resolvido com o .env (o mesmo caminho do make publicar).
senha=$(cd "$raiz" && docker compose -p jeje-pub -f compose.yaml -f compose.publicacao.yaml config --format json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["api"]["environment"]["ACESSO_SENHA"])')
area=$(mktemp -d)
trap 'rm -rf "$area"' EXIT
falhas=0

# O túnel conecta alguns segundos depois de a stack ficar saudável: espera até 2 min pela saúde.
for _ in $(seq 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$url/api/health")" = 200 ] && break
  sleep 2
done

conferir() {  # nome, esperado, obtido
  if [ "$2" = "$3" ]; then echo "ok    $1"; else echo "FALHA $1: esperado $2, veio $3"; falhas=$((falhas + 1)); fi
}
status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

conferir "página" 200 "$(status "$url/")"
conferir "cabeçalho anti-iframe (só a própria origem)" "SAMEORIGIN" "$(curl -sI "$url/" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-frame-options"{print $2}')"
conferir "saúde aberta" 200 "$(status "$url/api/health")"
conferir "personas sem acesso" 401 "$(status "$url/api/personas")"
conferir "documentação sem acesso" 401 "$(status "$url/api/docs")"
conferir "contrato sem acesso" 401 "$(status "$url/api/openapi.json")"
conferir "senha errada" 401 "$(status -X POST -H 'Content-Type: application/json' -d '{"senha":"chute-errado"}' "$url/api/acesso/entrada")"
corpo=$(python3 -c 'import json,sys; print(json.dumps({"senha": sys.argv[1]}))' "$senha")
conferir "senha certa" 204 "$(status -c "$area/cookies" -D "$area/cabecalhos" -X POST -H 'Content-Type: application/json' -d "$corpo" "$url/api/acesso/entrada")"
conferir "cookie seguro e HttpOnly" "sim" "$(grep -qi '^set-cookie:.*secure.*httponly\|^set-cookie:.*httponly.*secure' "$area/cabecalhos" && echo sim || echo não)"
conferir "personas com acesso" 200 "$(status -b "$area/cookies" "$url/api/personas")"

if [ "$conversa" = 1 ]; then
  json() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {}, {"d": d}))' "$1"; }
  pedir() { curl -s -b "$area/cookies" -H 'Content-Type: application/json' "$@"; }
  cliente=$(pedir "$url/api/personas" | json 'd[0]["customer_id"]')
  sessao=$(python3 -c 'import json,sys; print(json.dumps({"customer_id": sys.argv[1], "dispositivo": "cadastrado"}))' "$cliente")
  token=$(pedir -X POST -d "$sessao" "$url/api/sessoes" | json 'd["token"]')
  for idioma in es pt; do
    if [ "$idioma" = es ]; then frase="¿Por qué rechazaron mi compra?"; else frase="Por que recusaram minha compra?"; fi
    conversa_id=$(pedir -H "Authorization: Bearer $token" -X POST -d "{\"idioma\": \"$idioma\"}" "$url/api/conversas" | json 'd["conversa_id"]')
    texto=$(python3 -c 'import json,sys; print(json.dumps({"texto": sys.argv[1]}))' "$frase")
    pedir -H "Authorization: Bearer $token" -X POST -d "$texto" -o "$area/turno" -w '%{http_code}' "$url/api/conversas/$conversa_id/turnos" > "$area/codigo"
    conferir "conversa em $idioma: o turno responde" 200 "$(cat "$area/codigo")"
    conferir "conversa em $idioma: na língua da conversa" "$idioma" "$(json 'd.get("idioma")' < "$area/turno" 2>/dev/null || echo erro)"
    conferir "conversa em $idioma: com a regra que decidiu" sim "$(json '"sim" if d.get("regra") else "não"' < "$area/turno" 2>/dev/null || echo erro)"
  done
fi

[ "$falhas" -eq 0 ] && echo "publicação conferida em $url" || { echo "$falhas conferência(s) falharam" >&2; exit 1; }
