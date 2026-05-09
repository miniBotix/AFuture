"""
AgarLinx — Data Generator & Scheduler  (MFT-v4)
=================================================
Generates every 3 minutes:
  prices.json        ← XOR-encoded payload
  assets/s.css       ← --gl-seed token  (16 hex)
  assets/v.js        ← _ck token        (12 hex)

Key assembly mirrors _mk() in index.html EXACTLY:
  key = SECRET[:12] + ":" + date + ":" + hour_2digit
      + ":" + tb[:8] + ":" + vk[:6]

Run:
  pip install curl_cffi schedule
  python script.py
"""

import json, hmac, hashlib, random, base64, os, secrets, time, logging
from datetime import datetime

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL = True
except ImportError:
    HAS_CURL = False

try:
    import schedule
    HAS_SCHEDULE = True
except ImportError:
    HAS_SCHEDULE = False

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("AgarLinx")

# ─── Config ───────────────────────────────────────────────────────────────────
_SECRET      = "UlavarNamban_AgriData_2026_TN"
INTERVAL_MIN = 3
OUT_JSON     = "prices.json"
OUT_CSS      = os.path.join("assets", "s.css")
OUT_JS       = os.path.join("assets", "v.js")

# ─── Tamil Agricultural Proverbs ──────────────────────────────────────────────
PROVERBS = [
    {"ta": "உழவே தலைசிறந்த தொழில்",         "en": "Farming is the noblest profession"},
    {"ta": "நிலமும் உழைப்பும் செல்வம் தரும்", "en": "Land and labour bring prosperity"},
    {"ta": "வேளாண்மை இல்லாவிடில் வாழ்வில்லை", "en": "Without farming, there is no life"},
    {"ta": "மண்ணை நம்பு மழையை நம்பு",        "en": "Trust the soil, trust the rain"},
    {"ta": "விதைத்தவன் அறுவடை செய்வான்",      "en": "He who sows shall reap"},
    {"ta": "உழவன் இல்லாமல் உலகம் இல்லை",    "en": "No world without the farmer"},
    {"ta": "பயிர் வளர்ந்தால் நாடு வளரும்",    "en": "When crops grow, the nation grows"},
    {"ta": "நல்ல விதை நல்ல விளைச்சல்",       "en": "Good seed yields good harvest"},
]
QUALITY_CODES = ["QA7X", "QB3M", "QC9P", "QD2R", "QE5T"]
SEASON_TAGS   = ["kharif", "rabi", "zaid", "perennial"]

# ─── Fallback mock data ───────────────────────────────────────────────────────
MOCK_CROPS = [
    {"crop": "Copra",          "group": "Oil Seeds",   "base": 14012, "state": "Tamil Nadu"},
    {"crop": "Sesamum",        "group": "Oil Seeds",   "base": 11500, "state": "Tamil Nadu"},
    {"crop": "Niger Seed",     "group": "Oil Seeds",   "base": 10200, "state": "Karnataka"},
    {"crop": "Cotton",         "group": "Fibre Crops", "base": 8584,  "state": "Maharashtra"},
    {"crop": "Green Gram",     "group": "Pulses",      "base": 7800,  "state": "Rajasthan"},
    {"crop": "Black Gram",     "group": "Pulses",      "base": 7200,  "state": "Andhra Pradesh"},
    {"crop": "Groundnut",      "group": "Oil Seeds",   "base": 7100,  "state": "Gujarat"},
    {"crop": "Red gram/Arhar", "group": "Pulses",      "base": 6800,  "state": "Madhya Pradesh"},
    {"crop": "Lentil",         "group": "Pulses",      "base": 6500,  "state": "Uttar Pradesh"},
    {"crop": "Sunflower/Sun",  "group": "Oil Seeds",   "base": 6300,  "state": "Karnataka"},
    {"crop": "Mustard",        "group": "Oil Seeds",   "base": 5800,  "state": "Rajasthan"},
    {"crop": "Soyabean",       "group": "Oil Seeds",   "base": 5200,  "state": "Madhya Pradesh"},
    {"crop": "Bengal Gram",    "group": "Pulses",      "base": 4900,  "state": "Maharashtra"},
    {"crop": "Safflower",      "group": "Oil Seeds",   "base": 4700,  "state": "Karnataka"},
    {"crop": "Wheat",          "group": "Cereals",     "base": 2474,  "state": "Punjab"},
    {"crop": "Maize",          "group": "Cereals",     "base": 1883,  "state": "Bihar"},
    {"crop": "Paddy",          "group": "Cereals",     "base": 2561,  "state": "West Bengal"},
    {"crop": "Ragi",           "group": "Cereals",     "base": 3516,  "state": "Karnataka"},
    {"crop": "Jowar",          "group": "Cereals",     "base": 2800,  "state": "Maharashtra"},
    {"crop": "Bajra",          "group": "Cereals",     "base": 2400,  "state": "Rajasthan"},
    {"crop": "Rice",           "group": "Cereals",     "base": 3800,  "state": "Tamil Nadu"},
    {"crop": "Tomato",         "group": "Vegetables",  "base": 1200,  "state": "Maharashtra"},
    {"crop": "Onion",          "group": "Vegetables",  "base": 1800,  "state": "Maharashtra"},
    {"crop": "Potato",         "group": "Vegetables",  "base": 1400,  "state": "Uttar Pradesh"},
]

def make_mock_records(date_disp: str) -> list:
    records = []
    for c in MOCK_CROPS:
        trend   = random.choice(["up", "down", "stable"])
        noise   = random.uniform(-0.04, 0.04)
        price   = round(c["base"] * (1 + noise), 2)
        arrival = round(random.uniform(5, 800), 2)
        records.append({
            "crop":      c["crop"],
            "group":     c["group"],
            "price":     price,
            "arrival":   arrival,
            "date":      date_disp,
            "trend":     trend,
            "state":     c["state"],
            "district":  "",
            "market":    "",
            "min_price": round(price * 0.92, 2),
            "max_price": round(price * 1.08, 2),
        })
    return records


# ─── Key assembly — EXACT mirror of _mk() in index.html ──────────────────────
def combined_key(date_str: str, hour: int, tb: str, vk: str) -> str:
    """
    Mirrors JS _mk():
      const a = _S.slice(0,12);
      const b = d + ':' + String(h).padStart(2,'0');
      const c = tb.slice(0,8) + ':' + vk.slice(0,6);
      return [a,b,c].join(':');
    """
    a = _SECRET[:12]
    b = f"{date_str}:{hour:02d}"
    c = f"{tb[:8]}:{vk[:6]}"
    return f"{a}:{b}:{c}"


# ─── XOR-B64 — mirrors _xd() in index.html ───────────────────────────────────
def xor_encode(plaintext: str, key: str) -> str:
    pb = plaintext.encode("utf-8")
    kb = (key.encode("utf-8") * (len(pb) // len(key) + 2))[: len(pb)]
    return base64.b64encode(bytes(a ^ b for a, b in zip(pb, kb))).decode()


def make_sig(date_str: str, hour: int) -> str:
    raw = f"{_SECRET}:{date_str}:{hour:02d}"
    return hmac.new(raw.encode(), date_str.encode(), hashlib.sha256).hexdigest()


# ─── Fetch from AgMarkNet API ─────────────────────────────────────────────────
def fetch_all_records(date_str: str):
    url = "https://api.agmarknet.gov.in/v1/dashboard-data/"
    headers = {
        "accept":       "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin":       "https://agmarknet.gov.in",
        "referer":      "https://agmarknet.gov.in/",
        "user-agent":   (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    base_payload = {
        "dashboard": "marketwise_price_arrival",
        "date":      date_str,
        "group":     [100000],
        "commodity": [100001],
        "variety":   100021,
        "state":     100006,
        "grades":    [4],
        "limit":     30,
        "format":    "json",
    }

    try:
        if not HAS_CURL:
            raise RuntimeError("curl_cffi not available")

        ses = curl_requests.Session()
        r0  = ses.post(url, headers=headers, json=base_payload, timeout=15)
        r0.raise_for_status()
        first       = r0.json()
        total_pages = first.get("pagination", {}).get("total_pages", 1)
        log.info(f"API → {total_pages} page(s)")

        all_records = []
        for page in range(1, total_pages + 1):
            payload = {**base_payload, "page": page}
            res = ses.post(url, headers=headers, json=payload, timeout=15)
            if res.status_code != 200:
                log.warning(f"  page {page} failed ({res.status_code})")
                continue
            pd   = res.json()
            recs = pd.get("data", {}).get("records", [])
            log.info(f"  page {page}: {len(recs)} records")
            for item in recs:
                all_records.append({
                    "crop":      item.get("cmdt_name"),
                    "group":     item.get("cmdt_grp_name"),
                    "price":     float(item.get("as_on_price")   or 0),
                    "arrival":   float(item.get("as_on_arrival") or 0),
                    "date":      item.get("reported_date"),
                    "trend":     item.get("trend"),
                    "state":     item.get("state_name"),
                    "district":  item.get("dist_name"),
                    "market":    item.get("mkt_name"),
                    "min_price": float(item.get("min_price") or 0),
                    "max_price": float(item.get("max_price") or 0),
                })

        return all_records if all_records else None

    except Exception as e:
        log.warning(f"API fetch failed: {e}")
        return None


# ─── Write assets/s.css ───────────────────────────────────────────────────────
def write_css(tb: str) -> None:
    # JS regex: /--gl-seed\s*:\s*([0-9a-f]{16})/i
    # tb must be exactly 16 lowercase hex chars
    noise_vars = "\n".join(
        f"  --ag-{secrets.token_hex(3)}: #{secrets.token_hex(3)};"
        for _ in range(3)
    )
    content = (
        "/* AgarLinx asset token layer — do not edit */\n"
        ":root {\n"
        f"{noise_vars}\n"
        f"  --gl-seed: {tb};\n"
        f"  --ag-{secrets.token_hex(3)}: #{secrets.token_hex(3)};\n"
        "}\n"
        ".ag-token-layer { display: none; }\n"
    )
    os.makedirs("assets", exist_ok=True)
    with open(OUT_CSS, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"  assets/s.css → --gl-seed: {tb}")


# ─── Write assets/v.js ────────────────────────────────────────────────────────
def write_js(vk: str) -> None:
    # JS regex: /_ck\s*:\s*'([0-9a-f]{12})'/
    # vk must be exactly 12 lowercase hex chars
    decoys = [
        f"  _{secrets.token_hex(2)}: '{secrets.token_hex(4)}',",
        f"  _{secrets.token_hex(2)}: '{secrets.token_hex(4)}',",
        f"  _rv: {random.randint(1000, 9999)},",
    ]
    random.shuffle(decoys)
    decoys.insert(random.randint(0, len(decoys)), f"  _ck: '{vk}',")

    content = (
        "/* AgarLinx validation token layer — do not edit */\n"
        "(function(){\n"
        "  var _cfg={\n"
        + "\n".join(decoys) + "\n"
        "  };\n"
        "  if(typeof window!=='undefined')window.__agCfg=_cfg;\n"
        "})();\n"
    )
    os.makedirs("assets", exist_ok=True)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"  assets/v.js  → _ck: '{vk}'")


# ─── Atomic write helper ──────────────────────────────────────────────────────
def _atomic_write(path: str, content: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


# ─── Main generation job ──────────────────────────────────────────────────────
def generate() -> None:
    now       = datetime.now()
    date_str  = now.strftime("%Y-%m-%d")
    date_disp = now.strftime("%d-%m-%Y")
    hour      = now.hour

    log.info(f"─── Generate  {date_str}  hour={hour:02d} ───")

    # 1. Records
    records = fetch_all_records(date_str)
    if records:
        log.info(f"✓ API  → {len(records)} records")
    else:
        records = make_mock_records(date_disp)
        log.info(f"✓ Mock → {len(records)} records (API unavailable)")

    # 2. Fresh per-run tokens
    tb = secrets.token_hex(8)   # 16 hex
    vk = secrets.token_hex(6)   # 12 hex

    # 3. Encode
    key      = combined_key(date_str, hour, tb, vk)
    raw_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    encoded  = xor_encode(raw_json, key)

    # 4. Build output
    sig    = make_sig(date_str, hour)
    output = {
        "_v":       4,
        "_ts":      now.isoformat(),
        "_h":       hour,
        "_d":       date_disp,
        "_sig":     sig,
        "_c":       len(records),
        "payload":  encoded,
        "_proverb": random.choice(PROVERBS),
        "_season":  random.choice(SEASON_TAGS),
        "_n": {
            "alpha": base64.b64encode(random.randbytes(24)).decode(),
            "beta":  secrets.token_hex(16),
            "gamma": random.choice(QUALITY_CODES),
            "delta": random.choice(SEASON_TAGS),
        },
        "_ref": "உழவர் நம்பன் | Ulavarnanban",
        "_enc": "xor-b64-mft-v4",
    }

    # 5. Write files (assets first, then prices.json last so decoder
    #    always finds consistent token + payload)
    write_css(tb)
    write_js(vk)
    _atomic_write(OUT_JSON, json.dumps(output, ensure_ascii=False, indent=2))

    log.info(f"✅  Done!  key_prefix={key[:32]}…")
    log.info(f"    Files: {OUT_JSON}  {OUT_CSS}  {OUT_JS}")


# ─── Entry point ──────────────────────────────────────────────────────────────
def main() -> None:
    log.info("═══════════════════════════════════════════")
    log.info("  AgarLinx Data Generator  (MFT-v4)       ")
    log.info(f"  Interval : every {INTERVAL_MIN} minutes             ")
    log.info("  Files    : prices.json + assets/s.css   ")
    log.info("           + assets/v.js                  ")
    log.info("═══════════════════════════════════════════")

    # Run once immediately
    generate()

    if HAS_SCHEDULE:
        schedule.every(INTERVAL_MIN).minutes.do(generate)
        log.info(f"Scheduler active — next run in {INTERVAL_MIN} min (Ctrl+C to stop)")
        while True:
            schedule.run_pending()
            time.sleep(10)
    else:
        log.warning("'schedule' not installed — pip install schedule")
        log.info("Running manual loop…")
        while True:
            time.sleep(INTERVAL_MIN * 60)
            generate()


if __name__ == "__main__":
    main()
