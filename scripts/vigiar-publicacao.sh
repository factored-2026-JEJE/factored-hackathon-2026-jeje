#!/bin/sh
# A vigia da publicação durante o julgamento (DEV-021a, de 6 a 15/10), chamada pelos timers do
# systemd do usuário (ops/systemd, instalados por scripts/instalar-vigia.sh): a conferência pelo
# endereço público (com --conversa, a diária, em ES e PT) e o aviso no canal do .env quando o estado muda:
# quando ela passa a falhar e quando volta, sem repetir a cada 10 min enquanto a publicação segue fora.
# Depois de 16/10, não faz nada. O registro e o último estado de cada conferência ficam em ~/.local/state/jeje.
#
#   scripts/vigiar-publicacao.sh [--conversa] [endereço]
set -u
cd "$(dirname "$0")/.."
[ "$(date +%Y%m%d)" -gt 20261016 ] && exit 0
registro="${XDG_STATE_HOME:-$HOME/.local/state}/jeje/vigia.log"
mkdir -p "$(dirname "$registro")"
saida=$(scripts/conferir-publicacao.sh "$@" 2>&1)
status=$?
printf '%s %s status=%s\n%s\n' "$(date -Is)" "$*" "$status" "$saida" >> "$registro"
ultimo="$(dirname "$registro")/ultimo-status-$(printf '%s' "${*:-rapida}" | tr -c 'a-zA-Z0-9' '_')"
anterior=$(cat "$ultimo" 2>/dev/null || echo 0)
echo "$status" > "$ultimo"
if [ "$status" -ne 0 ] && [ "$anterior" -eq 0 ]; then
  falhas=$(printf '%s\n' "$saida" | grep -E '^FALHA|falharam' | head -n 3 | tr '\n' ' ')
  scripts/avisar.sh "A conferência da publicação falhou em $(date '+%d/%m %H:%M'): $falhas" || true
elif [ "$status" -eq 0 ] && [ "$anterior" -ne 0 ]; then
  scripts/avisar.sh "A publicação voltou em $(date '+%d/%m %H:%M'): a conferência passou de novo." || true
fi
exit "$status"
