#!/usr/bin/env python3
"""
Aire Rápido · fetch_junta.py · v1.4.0

Descarga los CSV diarios de la Red de Vigilancia y Control de la Calidad del
Aire de Andalucía (provincia de Cádiz), se queda con las estaciones del Campo
de Gibraltar y guarda un JSON compacto por día en data/AAAA/AAAA-MM-DD.json.

Fuente: Junta de Andalucía, Consejería de Sostenibilidad y Medio Ambiente.
Licencia de los datos: CC BY 4.0. Datos horarios NO validados.

Además guarda, para cada día, el polvo mineral en superficie estimado por el
modelo CAMS (Copernicus) en la Bahía de Algeciras, vía Open-Meteo, para
detectar posibles intrusiones de polvo africano. Es un modelo, no una medida.

Y mantiene data/miteco_intrusiones.json con los informes oficiales de
predicción de intrusiones de aire africano que publica el Ministerio
(MITECO, elaborados por el CSIC): fecha -> enlace al PDF.

Uso:
  python scripts/fetch_junta.py                 # hoy y ayer (hora de Madrid)
  python scripts/fetch_junta.py --desde 2024-01-01 --hasta 2024-12-31
  python scripts/fetch_junta.py --todas         # todas las estaciones de Cádiz
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

VERSION = "1.4.0"
BASE_URL = ("https://www.juntadeandalucia.es/medioambiente/atmosfera/"
            "informes_siva/cuantitativo/{y}/CA_{ymd}.csv")
PRIMER_DIA = dt.date(2021, 10, 25)  # inicio de la serie publicada en este formato
MUNICIPIOS_CG = ("ALGECIRAS", "BARRIOS", "LINEA", "SAN ROQUE", "TARIFA",
                 "CASTELLAR", "JIMENA")
POLVO_URL = ("https://air-quality-api.open-meteo.com/v1/air-quality"
             "?latitude=36.170&longitude=-5.420"
             "&hourly=dust,aerosol_optical_depth&timezone=Europe%2FMadrid"
             "&start_date={d0}&end_date={d1}")
MITECO = "https://www.miteco.gob.es"
MITECO_FN = (MITECO + "/es/calidad-y-evaluacion-ambiental/temas/atmosfera-y-calidad-del-aire/"
             "evaluacion-y-datos-de-calidad-del-aire/fuentes-naturales/")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TZ = ZoneInfo("Europe/Madrid")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.upper()).strip()


def clave_col(h):
    """Identifica qué es cada columna a partir de su cabecera."""
    k = re.sub(r"[^A-Z0-9]", "", norm(h))
    if k.startswith("PROV"): return "provincia"
    if k.startswith("MUNI"): return "municipio"
    if k.startswith("ESTA"): return "estacion"
    if k.startswith("FECH"): return "fecha"
    if k.startswith("HORA"): return "hora"
    if k.startswith("PM10"): return "PM10"
    if k.startswith("PM2"): return "PM2.5"
    if k.startswith("NO2"): return "NO2"
    if k.startswith("SO2"): return "SO2"
    if k.startswith("O3"): return "O3"
    if k.startswith("CO") and not k.startswith("CO2"): return "CO"
    return None


# Orden documentado (col. 1-6). A partir de la 7 es una suposición que solo
# se usa si el fichero no trae cabecera; el log lo avisará.
POSICIONAL = ["provincia", "municipio", "estacion", "fecha", "hora",
              "PM10", "PM2.5", "NO2", "O3", "SO2", "CO"]


def descargar(fecha, reintentos=3):
    url = BASE_URL.format(y=fecha.year, ymd=fecha.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={
        "User-Agent": f"AireRapido/{VERSION} (+github pages; uso personal)"})
    for i in range(reintentos):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read(), url
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, url
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(3 * (i + 1))
    print(f"  ! Error descargando {url}: {err}", file=sys.stderr)
    return None, url


def decodificar(raw):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def num(v):
    v = (v or "").strip().replace(",", ".")
    if not v or v in {"-", "--", "ND", "N/D"}:
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    return None if x < 0 else round(x, 1)


def parsear(texto, todas=False):
    muestra = texto[:4000]
    try:
        delim = csv.Sniffer().sniff(muestra, delimiters=";,\t|").delimiter
    except csv.Error:
        delim = ";"
    filas = [f for f in csv.reader(io.StringIO(texto), delimiter=delim)
             if any(c.strip() for c in f)]
    if not filas:
        return {}, []

    cab = [clave_col(h) for h in filas[0]]
    if "estacion" in cab and "hora" in cab:
        cols, cuerpo = cab, filas[1:]
    else:
        print("  ! Sin cabecera reconocible: uso orden posicional supuesto. "
              f"Primera fila: {filas[0]}", file=sys.stderr)
        cols, cuerpo = POSICIONAL[:len(filas[0])], filas

    idx = {c: i for i, c in enumerate(cols) if c}
    contaminantes = [c for c in cols if c in
                     ("SO2", "NO2", "PM10", "PM2.5", "O3", "CO")]

    registros, horas = [], []
    for f in cuerpo:
        g = lambda c: f[idx[c]] if c in idx and idx[c] < len(f) else ""
        mun, est = norm(g("municipio")), norm(g("estacion"))
        if not est:
            continue
        if not todas and not any(m in mun for m in MUNICIPIOS_CG):
            continue
        m = re.search(r"\d{1,2}", g("hora"))
        if not m:
            continue
        h = int(m.group())
        horas.append(h)
        registros.append((est, mun, h, {c: num(g(c)) for c in contaminantes}))

    base1 = not (horas and min(horas) == 0)  # 1..24 salvo que aparezca un 0
    out = {}
    for est, mun, h, vals in registros:
        i = h - 1 if base1 else h
        if not 0 <= i <= 23:
            continue
        e = out.setdefault(est, {"municipio": mun, "h": {}})
        for c, v in vals.items():
            serie = e["h"].setdefault(c, [None] * 24)
            if v is not None:
                serie[i] = v
    # quita contaminantes sin ningún dato
    for e in out.values():
        e["h"] = {c: s for c, s in e["h"].items() if any(x is not None for x in s)}
    return out, contaminantes


def polvo_rango(d0, d1):
    """Polvo CAMS por día: {fecha: {"polvo": [24], "aod": [24]}}.

    La hora j (etiqueta j+1, como en la Junta) toma el valor de las (j+1):00;
    la etiqueta 24 es las 00:00 del día siguiente.
    """
    out = {}
    ini = d0
    while ini <= d1:
        fin = min(d1, ini + dt.timedelta(59))
        url = POLVO_URL.format(d0=ini.isoformat(),
                               d1=(fin + dt.timedelta(1)).isoformat())
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"AireRapido/{VERSION}"})
            with urllib.request.urlopen(req, timeout=40) as r:
                j = json.loads(r.read().decode("utf-8"))
            h = j.get("hourly", {})
            por_hora = {}
            for t, du, ao in zip(h.get("time", []), h.get("dust", []),
                                 h.get("aerosol_optical_depth", [None] * len(h.get("time", [])))):
                por_hora[t] = (du, ao)
            f = ini
            while f <= fin:
                pol, aod = [], []
                for k in range(1, 25):
                    t = dt.datetime.combine(f, dt.time()) + dt.timedelta(hours=k)
                    du, ao = por_hora.get(t.strftime("%Y-%m-%dT%H:%M"), (None, None))
                    pol.append(None if du is None else round(float(du), 1))
                    aod.append(None if ao is None else round(float(ao), 2))
                if any(v is not None for v in pol):
                    out[f.isoformat()] = {"polvo": pol, "aod": aod}
                f += dt.timedelta(1)
        except Exception as e:  # noqa: BLE001
            print(f"  ! Polvo CAMS {ini}..{fin}: {e}", file=sys.stderr)
        ini = fin + dt.timedelta(1)
        time.sleep(0.5)
    return out


def pagina_miteco(y, m):
    """Página del Ministerio con las predicciones de ese mes (o del año, antes de ago-2023)."""
    if (y, m) >= (2023, 9):
        return MITECO_FN + f"episodios-{MESES[m-1]}-{y}.html"
    if (y, m) == (2023, 8):
        return MITECO_FN + "episodios_agosto_2023.html"
    return MITECO_FN + f"prediccion_episodios_{y}.html"


def fechas_de_titulo(texto, y, m_pagina=None):
    """'Predicción para los días 29, 30 y 31 de agosto' -> [date, date, date]."""
    t = norm(texto).lower()
    fichas = re.findall(r"\b(\d{1,2})\b|\b(" + "|".join(MESES) + r")\b", t)
    out, pendientes = [], []
    for num, mes in fichas:
        if num:
            pendientes.append(int(num))
        elif mes:
            mm = MESES.index(mes) + 1
            yy = y
            if m_pagina == 1 and mm == 12: yy = y - 1
            if m_pagina == 12 and mm == 1: yy = y + 1
            for d in pendientes:
                try:
                    out.append(dt.date(yy, mm, d))
                except ValueError:
                    pass
            pendientes = []
    return out


def fechas_de_pdf(url):
    """Respaldo: Prediccion_20260923.pdf / Prediccion_202609192021.pdf / Prediccion_20260829_30_31.pdf"""
    nombre = url.rsplit("/", 1)[-1]
    mt = re.search(r"(20\d{2})(\d{2})(\d{2})((?:_?\d{2})*)", nombre)
    if not mt:
        return []
    y, m = int(mt.group(1)), int(mt.group(2))
    dias = [int(mt.group(3))] + [int(x) for x in re.findall(r"\d{2}", mt.group(4))]
    out = []
    for d in dias:
        try:
            out.append(dt.date(y, m, d))
        except ValueError:
            pass
    return out


def parsear_miteco(html, y, m=None, pagina=""):
    res = {}
    for href, txt in re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        if "redicc" not in (txt + href).lower():
            continue
        url = href if href.startswith("http") else MITECO + href
        fechas = fechas_de_titulo(txt, y, m) or fechas_de_pdf(url)
        for f in fechas:
            res[f.isoformat()] = {"pdf": url, "titulo": txt, "pagina": pagina}
    return res


def miteco_actualizar(meses):
    """meses: lista de (año, mes). Devuelve dict fecha -> informe."""
    vistos, res = set(), {}
    for y, m in meses:
        url = pagina_miteco(y, m)
        if url in vistos:
            continue
        vistos.add(url)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"AireRapido/{VERSION}"})
            with urllib.request.urlopen(req, timeout=40) as r:
                html = r.read().decode("utf-8", errors="replace")
            nuevos = parsear_miteco(html, y, m if (y, m) >= (2023, 8) else None, url)
            res.update(nuevos)
            print(f"  MITECO {y}-{m:02d}: {len(nuevos)} día(s) con predicción")
        except Exception as e:  # noqa: BLE001
            print(f"  ! MITECO {url}: {e}", file=sys.stderr)
        time.sleep(0.5)
    return res


def guardar_json(ruta, obj):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, ruta)


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return defecto


def procesar(fecha, todas, ahora_iso, polvo=None):
    raw, url = descargar(fecha)
    if raw is None:
        print(f"  - {fecha}: sin fichero ({url})")
        return None
    est, conts = parsear(decodificar(raw), todas)
    if not est:
        print(f"  - {fecha}: fichero sin estaciones del ámbito")
        return None
    dia = {
        "v": 1,
        "fecha": fecha.isoformat(),
        "actualizado": ahora_iso,
        "fuente": url,
        "estaciones": est,
    }
    if polvo:
        dia.update(polvo)
    ruta = os.path.join(DATA, str(fecha.year), f"{fecha.isoformat()}.json")
    previo = leer_json(ruta, None)
    igual = lambda a, b: all(a.get(k) == b.get(k) for k in ("estaciones", "polvo", "aod"))
    if previo and igual(previo, dia):
        print(f"  = {fecha}: sin cambios")
    else:
        guardar_json(ruta, dia)
        print(f"  + {fecha}: {len(est)} estaciones, contaminantes {conts}")
    return dia


def ultima_hora(dia):
    ult = -1
    for e in dia["estaciones"].values():
        for s in e["h"].values():
            for i, v in enumerate(s):
                if v is not None and i > ult:
                    ult = i
    return ult


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde")
    ap.add_argument("--hasta")
    ap.add_argument("--todas", action="store_true",
                    help="guardar todas las estaciones de Cádiz")
    ap.add_argument("--pausa", type=float, default=1.0,
                    help="segundos entre descargas en cargas masivas")
    a = ap.parse_args()

    hoy = dt.datetime.now(TZ).date()
    if a.desde:
        d0 = max(dt.date.fromisoformat(a.desde), PRIMER_DIA)
        d1 = dt.date.fromisoformat(a.hasta) if a.hasta else hoy
        fechas = [d0 + dt.timedelta(n) for n in range((d1 - d0).days + 1)]
    else:
        fechas = [hoy - dt.timedelta(1), hoy]

    ahora_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Aire Rápido fetch v{VERSION}: {len(fechas)} día(s)")

    indice = set(leer_json(os.path.join(DATA, "index.json"), {}).get("fechas", []))
    detectadas = leer_json(os.path.join(DATA, "estaciones_detectadas.json"), {})
    polvo = polvo_rango(fechas[0], fechas[-1]) if fechas else {}
    print(f"Polvo CAMS: {len(polvo)} día(s)")
    ultimo = None
    for f in fechas:
        dia = procesar(f, a.todas, ahora_iso, polvo.get(f.isoformat()))
        if dia:
            indice.add(f.isoformat())
            for k, e in dia["estaciones"].items():
                detectadas.setdefault(k, {"municipio": e["municipio"],
                                          "visto_por_primera_vez": f.isoformat()})
            if ultimo is None or f >= dt.date.fromisoformat(ultimo["fecha"]):
                ultimo = dia
        if len(fechas) > 2:
            time.sleep(a.pausa)

    # informes oficiales del Ministerio (mes actual y anterior, o todo el rango en cargas históricas)
    meses = sorted({(f.year, f.month) for f in fechas} | {(hoy.year, hoy.month)})
    if not a.desde:
        prev = hoy.replace(day=1) - dt.timedelta(1)
        meses = sorted(set(meses) | {(prev.year, prev.month)})
    ruta_m = os.path.join(DATA, "miteco_intrusiones.json")
    previo_m = leer_json(ruta_m, {"v": 1, "dias": {}})
    nuevos_m = miteco_actualizar(meses)
    if nuevos_m:
        dias_m = {**previo_m.get("dias", {}), **nuevos_m}
        if dias_m != previo_m.get("dias"):
            guardar_json(ruta_m, {"v": 1, "actualizado": ahora_iso, "dias": dict(sorted(dias_m.items()))})

    guardar_json(os.path.join(DATA, "index.json"),
                 {"v": 1, "fechas": sorted(indice)})
    guardar_json(os.path.join(DATA, "estaciones_detectadas.json"),
                 dict(sorted(detectadas.items())))

    if ultimo:
        latest = leer_json(os.path.join(DATA, "latest.json"), {})
        nuevo = (ultimo["fecha"], ultima_hora(ultimo))
        previo = (latest.get("fecha"), latest.get("ultima_hora"))
        if nuevo != previo and (not previo[0] or nuevo[0] >= previo[0]):
            guardar_json(os.path.join(DATA, "latest.json"), {
                "v": 1,
                "fecha": ultimo["fecha"],
                "ultima_hora": ultima_hora(ultimo),
                "actualizado": ahora_iso,
            })
    return 0


if __name__ == "__main__":
    sys.exit(main())
