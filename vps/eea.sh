#!/usr/bin/env bash
# Aire Rápido · vps/eea.sh · v1.1.0
# Una vez al día: completa los últimos 10 días con datos de la Agencia Europea (EEA) y registra el estado
set -uo pipefail
cd "$(dirname "$0")/.."
exec 9>/tmp/aire-rapido.lock
flock 9
echo "=== $(date -Is) EEA inicio"
git pull --rebase --quiet || echo "  ! git pull falló"
if "$HOME/.venv-aire/bin/python" scripts/eea_fetch.py --desde "$(date -d '-10 day' +%F)"; then res=ok; else res=error; fi
./vps/estado.sh eea "$res"
git add data
if git diff --cached --quiet; then echo "Sin cambios"; else git commit -q -m "Datos EEA $(date -u +'%Y-%m-%d')" && git push -q && echo "Subido"; fi
echo "=== $(date -Is) EEA fin ($res)"
