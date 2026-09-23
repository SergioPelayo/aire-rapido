#!/usr/bin/env bash
# Aire Rápido · vps/estado.sh · v1.0.0
# Registra en data/estado.json la hora y el resultado de la última ejecución.
# Uso: estado.sh horaria|eea ok|error
cd "$(dirname "$0")/.."
python3 - "$1" "$2" <<'PY'
import datetime, json, sys
ruta = "data/estado.json"
try:
    d = json.load(open(ruta, encoding="utf-8"))
except Exception:
    d = {"v": 1}
d[sys.argv[1]] = {"ultima": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "resultado": sys.argv[2]}
with open(ruta, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False)
PY
