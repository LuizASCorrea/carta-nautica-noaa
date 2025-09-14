# noaa_backend.py — NOAA/NDBC proxy simples (usa station_table.txt p/ meta e realtime2 p/ dados)
from flask import Flask, request, jsonify
import requests
from datetime import datetime, timezone

app = Flask(__name__)

# CORS básico
@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp

# Metadados seed (Havaí) — caso o feed esteja fora do ar
STATION_META = {
    "51001": {"name": "N. Hawaiian", "lat": 22.2,  "lng": -157.9},
    "51002": {"name": "S. Hawaiian", "lat": 20.4,  "lng": -157.1},
    "51211": {"name": "Kaneohe Bay", "lat": 21.45, "lng": -157.73},
    "51212": {"name": "Waimea",      "lat": 21.68, "lng": -158.05},
    "51213": {"name": "Barbers Point","lat": 21.20,"lng": -158.12},
}
_meta_cache = None  # cache dinâmico carregado de station_table.txt

def load_meta_cache():
    """Carrega metadados da tabela station_table.txt (delimitada por '|')."""
    global _meta_cache
    if _meta_cache is not None:
        return _meta_cache
    cache = {}
    try:
        url = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        for ln in r.text.splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = [p.strip() for p in ln.split("|")]
            if len(parts) < 7:
                continue
            sid = parts[0]
            name = parts[4]
            location = parts[6]
            try:
                tokens = location.split()
                lat_str, lat_dir, lon_str, lon_dir = tokens[0], tokens[1], tokens[2], tokens[3]
                lat = float(lat_str) * (1 if lat_dir.upper().startswith("N") else -1)
                lon = float(lon_str) * (1 if lon_dir.upper().startswith("E") else -1)
            except Exception:
                lat = lon = None
            cache[sid] = {"name": name, "lat": lat, "lng": lon}
        _meta_cache = cache
    except Exception:
        _meta_cache = {}
    return _meta_cache

def get_station_meta(sid: str):
    if sid in STATION_META:
        return STATION_META[sid]
    cache = load_meta_cache()
    return cache.get(sid, {"name": None, "lat": None, "lng": None})

def parse_realtime2_text(text: str):
    """Lê o arquivo realtime2/<ID>.txt e pega WVHT (Hs), DPD (Tp), MWD (Dir)."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    hdr_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("#YY"):
            hdr_idx = i
            break
    if hdr_idx is None or hdr_idx + 1 >= len(lines):
        return {}

    header = lines[hdr_idx].lstrip("#").strip().split()
    row    = lines[hdr_idx + 1].split()
    cols = {name: idx for idx, name in enumerate(header)}

    def get(name):
        i = cols.get(name)
        if i is None or i >= len(row):
            return None
        v = row[i]
        return None if v == "MM" else v

    obs_time = None
    try:
        yy, mm, dd, hh, minu = (get('YY'), get('MM'), get('DD'), get('hh'), get('mm'))
        if all(v is not None for v in [yy, mm, dd, hh, minu]):
            y = int(yy)
            if y < 100: y += 2000
            obs_time = datetime(int(y), int(mm), int(dd), int(hh), int(minu), tzinfo=timezone.utc).isoformat()
    except Exception:
        obs_time = None

    def as_float(x):
        try: return float(x)
        except: return None
    def as_int(x):
        try: return int(float(x))
        except: return None

    return {
        "Hs":  as_float(get('WVHT')),
        "Tp":  as_int(get('DPD')),
        "Dir": as_int(get('MWD')),
        "time": obs_time
    }

def fetch_station_latest(sid: str):
    """Busca a última leitura de uma estação no realtime2/<ID>.txt."""
    url = f"https://www.ndbc.noaa.gov/data/realtime2/{sid}.txt"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        parsed = parse_realtime2_text(resp.text) or {}
    except Exception as e:
        parsed = {"error": str(e)}

    meta = get_station_meta(sid)
    return {
        "id": sid,
        "name": meta.get("name"),
        "lat": meta.get("lat"),
        "lng": meta.get("lng"),
        "Hs": parsed.get("Hs"),
        "Tp": parsed.get("Tp"),
        "Dir": parsed.get("Dir"),
        "time": parsed.get("time"),
        **({"error": parsed.get("error")} if parsed.get("error") else {})
    }

@app.get("/noaa")
def noaa_many():
    ids = request.args.get("ids", "").strip()
    if not ids:
        return jsonify({"error": "use ?ids=51001,51002,..."}), 400
    out = []
    for sid in [s.strip() for s in ids.split(",") if s.strip()]:
        out.append(fetch_station_latest(sid))
    return jsonify(out)

@app.get("/stations")
def stations():
    """Lista todas as estações com lat/lon do station_table.txt."""
    cache = load_meta_cache()
    out = []
    for sid, meta in cache.items():
        lat = meta.get("lat"); lng = meta.get("lng")
        if lat is None or lng is None:
            continue
        out.append({"id": sid, "name": meta.get("name"), "lat": lat, "lng": lng})
    return jsonify(out)

if __name__ == "__main__":
    load_meta_cache()
    app.run(host="0.0.0.0", port=5001, debug=True)
