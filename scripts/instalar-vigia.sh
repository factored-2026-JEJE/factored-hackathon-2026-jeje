#!/bin/sh
# Instala a vigia da publicação (DEV-021a) nos timers do systemd do usuário, para o repositório da
# publicação (o checkout onde o make publicar roda, com o .env): a conferência rápida a cada 10 min e
# o teste diário em ES e PT às 9h. O systemd do usuário roda também sem sessão aberta com o linger
# (loginctl enable-linger), que é de quem administra a máquina.
#
#   scripts/instalar-vigia.sh            instala e liga os timers
#   scripts/instalar-vigia.sh --desligar desliga os timers (depois do julgamento)
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
destino="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
if [ "${1:-}" = "--desligar" ]; then
  systemctl --user disable --now jeje-vigia.timer jeje-teste-diario.timer
  exit 0
fi
mkdir -p "$destino"
for f in "$repo"/ops/systemd/*.in; do
  sed "s|@REPO@|$repo|g" "$f" > "$destino/$(basename "$f" .in)"
done
systemctl --user daemon-reload
systemctl --user enable --now jeje-vigia.timer jeje-teste-diario.timer
systemctl --user list-timers 'jeje-*' --no-pager
