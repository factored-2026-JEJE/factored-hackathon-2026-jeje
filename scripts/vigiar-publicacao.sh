#!/bin/sh
# A vigia da publicação durante o julgamento (DEV-021a, de 6 a 15/10), chamada pelos timers do
# systemd do usuário (ops/systemd, instalados por scripts/instalar-vigia.sh): a conferência pelo
# endereço público (com --conversa, a diária, em ES e PT) e, se ela falhar, o aviso no canal do .env.
# Depois de 16/10, não faz nada. O registro fica em ~/.local/state/jeje/vigia.log.
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
if [ "$status" -ne 0 ]; then
  falhas=$(printf '%s\n' "$saida" | grep -E '^FALHA|falharam' | head -n 3 | tr '\n' ' ')
  scripts/avisar.sh "A conferência da publicação falhou em $(date '+%d/%m %H:%M'): $falhas" || true
fi
exit "$status"
