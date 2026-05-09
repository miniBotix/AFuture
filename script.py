"""
AgarLinx — Data Generator  (MFT-v4)
====================================
Generates three files that work together with index.html's MFT-v4 decoder:

  prices.json      ← XOR-encoded market data + metadata
  assets/s.css     ← CSS token file containing --gl-seed (16 hex chars)
  assets/v.js      ← JS  token file containing _ck        (12 hex chars)

Key assembly (must mirror _mk() in index.html exactly):
  combined_key = SECRET[:12] + ":" + date + ":" + hour_padded
               + ":" + tb[:8]  + ":" + vk[:6]

Where:
  tb  = the 16-hex value in --gl-seed  (from assets/s.css)
  vk  = the 12-hex value in _ck        (from assets/v.js)

Run:
  python script.py

Requirements:
  pip install curl_cffi
"""

import json
import hmac
import hashlib
import random
import base64
import os
import secrets
from datetime import datetime
from curl_cffi import requests as curl_requests

# ─── Tamil Agricultural Proverbs (cultural noise metadata) ───────────────────
PROVERBS = [
    {"ta": "உழவே தலைசிறந்த தொழில்",         "en": "Farming is the noblest profession"},
    {"ta": "நிலமும் உழைப்பும் செல்வம் தரும்", "en": "Land and labour bring prosperity"},
    {"ta": "வேளாண்மை இல்லாவிடில் வாழ்வில்லை", "en": "Without farming, there is no life"},
    {"ta": "மண்ணை நம்பு மழையை நம்பு",        "en": "Trust the soil, trust the rain"},
    {"ta": "விதைத்தவன் அறுவடை செய்வான்",      "en": "He who sows shall reap"},
    {"ta": "உழவன் இல்லாமல் உலகம் இல்லை",    "en": "No world without the farmer"},
    {"ta": "பயிர் வளர்ந்தால் நாடு வளரும்",    "en": "When crops grow, the nation grows"},
    {"ta": "நல்ல விதை நல்ல விளைச்சல்",       "en": "Good seed yields good harvest"},
    {"ta": "மழை பெய்தால் வளம் பெருகும்",     "en": "Rain brings abundance"},
    {"ta": "உழவரே உலகின் உயிர்நாடி",         "en": "Farmers are the lifeblood of the world"},
    {"ta": "ஆற்றில் போட்டாலும் அளந்து போடு",  "en": "Measure even what you throw in the river"},
    {"ta": "கஷ்டமின்றி லாபமில்லை",           "en": "No gain without pain"},
]

SEASON_TAGS   = ["kharif", "rabi", "zaid", "perennial"]
QUALITY_CODES = ["QA7X", "QB3M", "QC9P", "QD2R", "QE5T"]

# ─── Master secret (same string used in index.html) ──────────────────────────
_SECRET = "UlavarNamban_AgriData_2026_TN"


# ─── Token generators ─────────────────────────────────────────────────────────

def gen_token_seed(length: int = 16) -> str:
    """Generate a random lowercase hex token of the given length."""
    return secrets.token_hex(length // 2)   # token_hex(8) → 16 hex chars


# ─── Key assembly — mirrors _mk() in index.html exactly ──────────────────────

def combined_key(date_str: str, hour: int, tb: str, vk: str) -> str:
    """
    Matches JS:
      const a = _S.slice(0,12);
      const b = d + ":" + String(h).padStart(2,'0');
      const c = tb.slice(0,8) + ":" + vk.slice(0,6);
      return [a,b,c].join(':');
    """
    a = _SECRET[:12]                           # "UlavarNamban"
    b = f"{date_str}:{hour:02d}"
    c = f"{tb[:8]}:{vk[:6]}"
    return f"{a}:{b}:{c}"


# ─── XOR-B64 encoder — mirrors _xd() in index.html ───────────────────────────

def xor_encode(plaintext: str, key: str) -> str:
    pb = plaintext.encode("utf-8")
    kb = (key.encode("utf-8") * (len(pb) // len(key) + 2))[: len(pb)]
    return base64.b64encode(bytes(a ^ b for a, b in zip(pb, kb))).decode()


# ─── HMAC signature (informational, not used for decoding) ───────────────────

def make_sig(date_str: str, hour: int) -> str:
    raw = f"{_SECRET}:{date_str}:{hour:02d}"
    return hmac.new(raw.encode(), date_str.encode(), hashlib.sha256).hexdigest()


# ─── Fetch data from AgMarkNet ────────────────────────────────────────────────

def fetch_all_records(ses, date_str: str) -> list:
    url = "https://api.agmarknet.gov.in/v1/dashboard-data/"
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://agmarknet.gov.in",
        "referer": "https://agmarknet.gov.in/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    base_payload = {
        "dashboard": "marketwise_price_arrival",
        "date": date_str,
        "group": [100000],
        "commodity": [100001],
        "variety": 100021,
        "state": 100006,
        "grades": [4],
        "limit": 30,
        "format": "json",
    }

    r0 = ses.post(url, headers=headers, json=base_payload)
    r0.raise_for_status()
    first = r0.json()

    total_pages = first.get("pagination", {}).get("total_pages", 1)
    print(f"  Total pages: {total_pages}")

    all_records = []
    for page in range(1, total_pages + 1):
        payload = {**base_payload, "page": page}
        res = ses.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            print(f"  ✗ page {page} failed ({res.status_code})")
            continue
        pd = res.json()
        recs = pd.get("data", {}).get("records", [])
        print(f"  ✓ page {page}: {len(recs)} records")

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

    return all_records


# ─── Write asset files ────────────────────────────────────────────────────────

def write_assets(tb: str, vk: str) -> None:
    """
    Write assets/s.css and assets/v.js.

    s.css  must contain:   --gl-seed: <tb>
    v.js   must contain:   _ck: '<vk>'

    The JS regex patterns in index.html:
      _p1 = /--gl-seed\s*:\s*([0-9a-f]{16})/i   ← matches tb (16 hex)
      _p2 = /_ck:\s*'([0-9a-f]{12})'/            ← matches vk (12 hex)
    """
    os.makedirs("assets", exist_ok=True)

    # ── assets/s.css ──────────────────────────────────────────────────────────
    # Embed token inside a realistic-looking CSS variable block.
    # Surround it with decoy noise variables so it doesn't stand out.
    decoy_vars = "\n".join([
        f"  --ag-{secrets.token_hex(3)}: #{secrets.token_hex(3)};",
        f"  --ag-{secrets.token_hex(3)}: #{secrets.token_hex(3)};",
        f"  --gl-seed: {tb};",          # ← THIS is what the decoder reads
        f"  --ag-{secrets.token_hex(3)}: #{secrets.token_hex(3)};",
        f"  --ag-{secrets.token_hex(3)}: #{secrets.token_hex(3)};",
    ])
    css_content = f"""\
/* AgarLinx — Asset Token Layer  [generated] */
/* Do not edit manually. Regenerated every hour by script.py */

:root {{
{decoy_vars}
}}

/* Render tokens — layout support variables */
.ag-token-layer {{
  display: none;
  visibility: hidden;
}}
"""
    with open("assets/s.css", "w", encoding="utf-8") as f:
        f.write(css_content)
    print("  ✓ assets/s.css written")

    # ── assets/v.js ───────────────────────────────────────────────────────────
    # Embed token inside a realistic-looking JS config object.
    decoy_keys = [
        f"  _{secrets.token_hex(2)}: '{secrets.token_hex(4)}',",
        f"  _ck: '{vk}',",             # ← THIS is what the decoder reads
        f"  _{secrets.token_hex(2)}: '{secrets.token_hex(4)}',",
        f"  _{secrets.token_hex(2)}: {random.randint(100, 999)},",
    ]
    random.shuffle(decoy_keys)
    # Re-insert _ck at a random position (shuffle may have moved it fine, ensure it's present)
    # Actually just build fresh with _ck guaranteed:
    lines = [
        f"  _{secrets.token_hex(2)}: '{secrets.token_hex(4)}',",
        f"  _ck: '{vk}',",
        f"  _{secrets.token_hex(2)}: '{secrets.token_hex(4)}',",
        f"  _rv: {random.randint(1000, 9999)},",
        f"  _{secrets.token_hex(2)}: '{secrets.token_hex(3)}',",
    ]
    js_content = f"""\
/* AgarLinx — Validation Token Layer  [generated] */
/* Do not edit manually. Regenerated every hour by script.py */

(function(){{
  var _cfg = {{
{chr(10).join(lines)}
  }};
  if(typeof window!=='undefined')window.__agCfg=_cfg;
}})();
"""
    with open("assets/v.js", "w", encoding="utf-8") as f:
        f.write(js_content)
    print("  ✓ assets/v.js written")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ses = curl_requests.Session()

    now       = datetime.now()
    date_str  = now.strftime("%Y-%m-%d")
    date_disp = now.strftime("%d-%m-%Y")
    hour      = now.hour

    print(f"\n🌾  AgarLinx Data Generator  (MFT-v4)")
    print(f"    Date: {date_str}  |  Hour: {hour:02d}\n")

    # ── 1. Fetch market data ──────────────────────────────────────────────────
    print("→ Fetching market data from AgMarkNet…")
    records = fetch_all_records(ses, date_str)
    print(f"  Total records: {len(records)}\n")

    # ── 2. Generate fresh per-hour tokens ────────────────────────────────────
    tb = gen_token_seed(16)   # 16-hex   → goes into assets/s.css as --gl-seed
    vk = gen_token_seed(12)   # 12-hex   → goes into assets/v.js  as _ck
    print(f"→ Generated tokens:  tb={tb}  |  vk={vk}")

    # ── 3. Build combined key and encode payload ──────────────────────────────
    key     = combined_key(date_str, hour, tb, vk)
    raw_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    encoded  = xor_encode(raw_json, key)
    print(f"   Combined key prefix: {key[:24]}…")

    # ── 4. Build HMAC signature ───────────────────────────────────────────────
    sig = make_sig(date_str, hour)

    # ── 5. Build noise / decoy metadata ──────────────────────────────────────
    proverb = random.choice(PROVERBS)
    noise   = {
        "alpha": base64.b64encode(random.randbytes(24)).decode(),
        "beta":  secrets.token_hex(16),
        "gamma": random.choice(QUALITY_CODES),
        "delta": random.choice(SEASON_TAGS),
    }

    # ── 6. Write prices.json ──────────────────────────────────────────────────
    output = {
        # Real metadata consumed by the decoder
        "_v":      4,                   # MFT version — index.html checks this
        "_ts":     now.isoformat(),
        "_h":      hour,
        "_d":      date_disp,
        "_sig":    sig,
        "_c":      len(records),
        "payload": encoded,
        # Cultural layer
        "_proverb": proverb,
        "_season":  random.choice(SEASON_TAGS),
        # Noise / decoys
        "_n":   noise,
        "_ref": "உழவர் நம்பன் | Ulavarnanban",
        "_enc": "xor-b64-mft-v4",
    }

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n→ prices.json written  ({len(records)} records)")

    # ── 7. Write asset token files ────────────────────────────────────────────
    print("\n→ Writing asset token files…")
    write_assets(tb, vk)

    print(f"\n✅  Done!  sig={sig[:12]}…")
    print(f"\n   File layout expected by index.html:")
    print(f"   ├── index.html")
    print(f"   ├── prices.json")
    print(f"   └── assets/")
    print(f"       ├── s.css")
    print(f"       └── v.js")
    print(f"\n   ⚠  All three files must be served together.")
    print(f"   ⚠  Re-run every hour (tokens rotate with the hour).")


if __name__ == "__main__":
    main()
