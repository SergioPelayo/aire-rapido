#!/usr/bin/env python3
"""
Aire Rápido · eea_fetch.py · v1.0.0

Completa los datos de la Junta con los de la Agencia Europea de Medio Ambiente
(EEA, Air Quality Download Service) para los contaminantes que la Junta no
publica en sus ficheros horarios de una cabina (por ejemplo, el PM10 de Palmones).

Nunca sobrescribe un dato de la Junta: solo rellena contaminantes ausentes o
vacíos, y los marca con "src": {"PM10": "EEA"} en el JSON del día.

Fuentes: E1a (datos validados, hasta el año pasado) y E2a (datos en tiempo real,
sin validar). Requiere pandas y pyarrow.

Uso:
  eea_fetch.py --informe              solo informa de lo que aporta la EEA
  eea_fetch.py                        informe y completa todo el histórico
  eea_fetch.py --desde 2026-09-01     completa solo desde esa fecha (uso diario)
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo

VERSION = "1.0.0"
API = "https://eeadmz1-downloads-api-appservice.azurewebsites.net/"
METADATA = "https://discomap.eea.europa.eu/map/fme/metadata/PanEuropean_metadata.csv"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TZ = ZoneInfo("Europe/Madrid")
PRIMER = dt.date(2021, 10, 25)
IDS = {1: "SO2", 8: "NO2", 5: "PM10", 6001: "PM2.5", 7: "O3", 10: "CO"}
NOTACION = {v: k for k, v in IDS.items()}
UA = {"User-Agent": f"AireRapido/{VERSION}"}


def log(*a):
    print(*a, flush=True)


def http(url, body=None, timeout=300):
    data = None if body is None else json.dumps(body).encode()
    hdr = dict(UA)
    if body is not None:
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdr)
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {err}")


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return defecto


def guardar_json(ruta, obj):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ruta)


# ---------- estaciones: stations.json + metadatos EEA ----------
def estaciones():
    st = leer_json(os.path.join(ROOT, "stations.json"), {}).get("estaciones", {})
    return {c["eea"]: clave for clave, c in st.items() if c.get("eea")}


def metadatos(codigos):
    """Puntos de muestreo y huso horario de cada estación, desde el fichero de metadatos."""
    ruta = "/tmp/eea_metadata.csv"
    if not os.path.exists(ruta) or time.time() - os.path.getmtime(ruta) > 7 * 86400:
        log("Descargando metadatos EEA…")
        with open(ruta, "wb") as fh:
            fh.write(http(METADATA))
    puntos, husos = defaultdict(set), {}
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        cab = fh.readline().rstrip("\r\n").split("\t")
        i = {n: k for k, n in enumerate(cab)}
        for linea in fh:
            f = linea.rstrip("\r\n").split("\t")
            if len(f) < len(cab) or f[i["Countrycode"]] != "ES":
                continue
            eoi = f[i["AirQualityStationEoICode"]]
            if eoi not in codigos:
                continue
            pol = f[i["AirPollutantCode"]].rsplit("/", 1)[-1]
            if pol.isdigit() and int(pol) in IDS:
                puntos[eoi].add(f[i["SamplingPoint"]].split("/")[-1])
            m = re.search(r"UTC([+-]\d{1,2})", f[i["Timezone"]])
            if m:
                husos[eoi] = int(m.group(1))
    return puntos, husos


# ---------- descarga de ficheros parquet ----------
def lista_urls(dataset):
    """URLs de los parquet de España para nuestros 6 contaminantes (prueba notación y URI)."""
    for pols in (list(NOTACION), [f"http://dd.eionet.europa.eu/vocabulary/aq/pollutant/{n}" for n in IDS]):
        cuerpo = {"countries": ["ES"], "cities": [], "pollutants": pols, "dataset": dataset, "source": "API"}
        try:
            txt = http(API + "ParquetFile/urls", cuerpo).decode("utf-8", "replace")
        except RuntimeError as e:
            log(f"  ! {e}")
            continue
        urls = [l.strip().strip('"') for l in txt.splitlines() if l.strip().lower().startswith(("http", '"http'))]
        if urls:
            return urls
    return []


def col(df, *nombres):
    bajos = {c.lower(): c for c in df.columns}
    for n in nombres:
        if n.lower() in bajos:
            return bajos[n.lower()]
    return None


def leer_parquet(contenido, huso):
    """Devuelve [(pol, fecha_local, indice_hora 0-23, valor)] con horas como en la Junta (01..24)."""
    import pandas as pd
    df = pd.read_parquet(io.BytesIO(contenido))
    c_pol, c_ini, c_fin = col(df, "Pollutant"), col(df, "Start"), col(df, "End")
    c_val, c_agg, c_vld = col(df, "Value"), col(df, "AggType"), col(df, "Validity")
    if not (c_pol and c_ini and c_fin and c_val):
        raise ValueError(f"columnas inesperadas: {list(df.columns)}")
    if c_vld:
        df = df[df[c_vld] > 0]
    df = df[df[c_val].notna() & (df[c_val] >= 0)]
    tz = dt.timezone(dt.timedelta(hours=huso))
    out = []
    for pol_id, ini, fin, val, agg in zip(df[c_pol], df[c_ini], df[c_fin], df[c_val],
                                          df[c_agg] if c_agg else ["hour"] * len(df)):
        try:
            pol = IDS.get(int(pol_id))
        except (TypeError, ValueError):
            pol = None
        if not pol:
            continue
        ini, fin = pd.Timestamp(ini).to_pydatetime(), pd.Timestamp(fin).to_pydatetime()
        diaria = str(agg).lower().startswith("day") or (fin - ini) >= dt.timedelta(hours=23)
        if diaria:                      # media diaria: se guarda a las 24:00, como la media de 24 h de la Junta
            out.append((pol, ini.date(), 23, round(float(val), 1)))
            continue
        local = fin.replace(tzinfo=tz).astimezone(TZ)
        if local.hour == 0:
            out.append((pol, local.date() - dt.timedelta(1), 23, round(float(val), 1)))
        else:
            out.append((pol, local.date(), local.hour - 1, round(float(val), 1)))
    return out


# ---------- principal ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--informe", action="store_true", help="solo informar, sin tocar data/")
    ap.add_argument("--desde", help="completar solo desde esta fecha (AAAA-MM-DD)")
    a = ap.parse_args()
    desde = max(dt.date.fromisoformat(a.desde), PRIMER) if a.desde else PRIMER

    mapa = estaciones()
    if not mapa:
        sys.exit("stations.json no tiene códigos 'eea'")
    puntos, husos = metadatos(set(mapa))
    log(f"Aire Rápido eea_fetch v{VERSION}: {len(mapa)} cabinas con código EEA, desde {desde}")

    serie = defaultdict(dict)          # (clave, pol) -> {fecha: [24]}
    fuentes = defaultdict(set)
    datasets = [(2, "E1a validados")] if not a.desde else []
    datasets.append((1, "E2a tiempo real"))
    if a.desde and desde.year < dt.date.today().year:
        datasets.insert(0, (2, "E1a validados"))
    for ds, nombre in datasets:
        urls = lista_urls(ds)
        mias = []
        for u in urls:
            fich = u.rsplit("/", 1)[-1]
            for eoi, sps in puntos.items():
                if eoi in fich or any(sp and sp in fich for sp in sps):
                    mias.append((eoi, u))
                    break
        log(f"{nombre}: {len(urls)} ficheros de España, {len(mias)} de nuestras cabinas")
        if urls and not mias:
            log("  Ejemplos de nombres de fichero:", [u.rsplit('/', 1)[-1] for u in urls[:5]])
        for eoi, u in mias:
            try:
                filas = leer_parquet(http(u), husos.get(eoi, 1))
            except Exception as e:  # noqa: BLE001
                log(f"  ! {eoi} {u.rsplit('/', 1)[-1]}: {e}")
                continue
            clave = mapa[eoi]
            for pol, fecha, idx, val in filas:
                if fecha < desde:
                    continue
                s = serie[(clave, pol)].setdefault(fecha, [None] * 24)
                if s[idx] is None:                     # E1a manda; E2a solo rellena
                    s[idx] = val
                    fuentes[(clave, pol)].add(nombre.split()[0])

    # ---------- informe: Junta frente a EEA ----------
    indice = leer_json(os.path.join(DATA, "index.json"), {}).get("fechas", [])
    junta = defaultdict(int)
    dias = {}
    for f in indice:
        if f < desde.isoformat():
            continue
        d = leer_json(os.path.join(DATA, f[:4], f + ".json"), None)
        if not d:
            continue
        dias[f] = d
        for clave, e in d["estaciones"].items():
            for pol, s in e.get("h", {}).items():
                if (e.get("src") or {}).get(pol) == "EEA":
                    continue
                if any(v is not None for v in s):
                    junta[(clave, pol)] += 1
    log("\nLo que tiene la EEA de cada cabina (solo contaminantes con datos EEA):")
    log("Cabina                          Contam.  días Junta  días EEA   aporta EEA")
    aporta = []
    for clave in sorted(set(mapa.values())):
        for pol in ["SO2", "NO2", "PM10", "PM2.5", "O3", "CO"]:
            dj = junta.get((clave, pol), 0)
            de = serie.get((clave, pol), {})
            de_n = sum(1 for s in de.values() if any(v is not None for v in s))
            if not de_n:
                continue
            nuevo = sum(1 for f, s in de.items() if any(v is not None for v in s)
                        and f.isoformat() in dias and not any(
                            v is not None for v in dias[f.isoformat()]["estaciones"].get(clave, {}).get("h", {}).get(pol, [None])))
            marca = f"+{nuevo} días ({'/'.join(sorted(fuentes[(clave, pol)]))})" if nuevo else ""
            if nuevo:
                aporta.append((clave, pol, nuevo))
            log(f"{clave[:31]:31} {pol:6} {dj:10} {de_n:9}   {marca}")
    log("\nRESUMEN: la EEA aporta datos que la Junta no publica en " + (", ".join(f"{c} {p} (+{n} días)" for c, p, n in aporta) if aporta else "ninguna cabina"))
    if a.informe:
        return 0

    # ---------- completar data/ ----------
    cambiados = 0
    for (clave, pol), porfecha in serie.items():
        for fecha, s in porfecha.items():
            f = fecha.isoformat()
            d = dias.get(f)
            if not d or clave not in d["estaciones"] or not any(v is not None for v in s):
                continue
            e = d["estaciones"][clave]
            actual = e.get("h", {}).get(pol)
            if actual and any(v is not None for v in actual) and (e.get("src") or {}).get(pol) != "EEA":
                continue                           # la Junta ya lo publica: no se toca
            if actual == s:
                continue
            e.setdefault("h", {})[pol] = s
            e.setdefault("src", {})[pol] = "EEA"
            d["_mod"] = True
    for f, d in dias.items():
        if d.pop("_mod", False):
            guardar_json(os.path.join(DATA, f[:4], f + ".json"), d)
            cambiados += 1
    log(f"\nDías actualizados con datos EEA: {cambiados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
