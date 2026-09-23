#!/usr/bin/env bash
# Aire Rápido · vps/actualizar.sh · v1.1.0
# Descarga Junta + polvo CAMS + informes MITECO, registra el estado y sube los datos a GitHub.
# Uso: actualizar.sh [--desde AAAA-MM-DD [--hasta AAAA-MM-DD]]
set -uo pipefail
cd "$(dirname "$0")/.."
exec 9>/tmp/aire-rapido.lock
flock -n 9 || { echo "$(date -Is) ya hay una ejecución en marcha"; exit 0; }
echo "=== $(date -Is) inicio $*"
git pull --rebase --quiet || echo "  ! git pull falló"
if python3 scripts/fetch_junta.py "$@"; then res=ok; else res=error; fi
./vps/estado.sh horaria "$res"
git add data
if git diff --cached --quiet; then
  echo "Sin cambios"
else
  git commit -q -m "Datos $(date -u +'%Y-%m-%d %H:%M') UTC (VPS)" && git push -q && echo "Subido"
fi
echo "=== $(date -Is) fin ($res)"
