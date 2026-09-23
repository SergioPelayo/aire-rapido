#!/usr/bin/env bash
# Aire Rápido · vps/eea.sh · v1.0.0
# Una vez al día: completa los últimos 10 días con datos de la Agencia Europea (EEA)
set -euo pipefail
cd "$(dirname "$0")/.."
exec 9>/tmp/aire-rapido.lock
flock 9
echo "=== $(date -Is) EEA inicio"
git pull --rebase --quiet
"$HOME/.venv-aire/bin/python" scripts/eea_fetch.py --desde "$(date -d '-10 day' +%F)"
git add data
if git diff --cached --quiet; then echo "Sin cambios"; else git commit -q -m "Datos EEA $(date -u +'%Y-%m-%d')" && git push -q && echo "Subido"; fi
echo "=== $(date -Is) EEA fin"
