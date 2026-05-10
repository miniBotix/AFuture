import json
import hmac
import hashlib
import random
import base64
from datetime import datetime
from curl_cffi import requests as curl_requests

# ─── Tamil Agricultural Proverbs (noise/cultural metadata) ────────────────────
PROVERBS = [
    {"ta": "உழவே தலைசிறந்த தொழில்",        "en": "Farming is the noblest profession"},
    {"ta": "நிலமும் உழைப்பும் செல்வம் தரும்", "en": "Land and labour bring prosperity"},
    {"ta": "வேளாண்மை இல்லாவிடில் வாழ்வில்லை","en": "Without farming, there is no life"},
    {"ta": "மண்ணை நம்பு மழையை நம்பு",       "en": "Trust the soil, trust the rain"},
    {"ta": "விதைத்தவன் அறுவடை செய்வான்",     "en": "He who sows shall reap"},
    {"ta": "உழவன் இல்லாமல் உலகம் இல்லை",   "en": "No world without the farmer"},
    {"ta": "பயிர் வளர்ந்தால் நாடு வளரும்",   "en": "When crops grow, the nation grows"},
    {"ta": "நல்ல விதை நல்ல விளைச்சல்",      "en": "Good seed yields good harvest"},
    {"ta": "மழை பெய்தால் வளம் பெருகும்",    "en": "Rain brings abundance"},
    {"ta": "உழவரே உலகின் உயிர்நாடி",        "en": "Farmers are the lifeblood of the world"},
    {"ta": "ஆற்றில் போட்டாலும் அளந்து போடு", "en": "Measure even what you throw in the river"},
    {"ta": "கஷ்டமின்றி லாபமில்லை",          "en": "No gain without pain"},
]

SEASON_TAGS = ["kharif", "rabi", "zaid", "perennial"]
QUALITY_CODES = ["QA7X", "QB3M", "QC9P", "QD2R", "QE5T"]

_SECRET = "UlavarNamban_AgriData_2026_TN"

# ─── Signing ──────────────────────────────────────────────────────────────────
def make_sig(date_str: str, hour: int) -> str:
    raw = f"{_SECRET}:{date_str}:{hour:02d}"
    return hmac.new(raw.encode(), date_str.encode(), hashlib.sha256).hexdigest()

# ─── XOR Encode ──────────────────────────────────────────────────────────────
def xor_encode(plaintext: str, key: str) -> str:
    pb = plaintext.encode("utf-8")
    kb = (key.encode("utf-8") * (len(pb) // len(key) + 2))[:len(pb)]
    return base64.b64encode(bytes(a ^ b for a, b in zip(pb, kb))).decode()

# ─── Build XOR key (must mirror JS decoder) ──────────────────────────────────
def make_xor_key(date_str: str, hour: int) -> str:
    return f"{_SECRET[:12]}:{date_str}:{hour:02d}"

# ─── Fetch ────────────────────────────────────────────────────────────────────
def fetch_all_records(ses, date_str):
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
    print(f"Total pages: {total_pages}")

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
            cleaned = {
                "crop":     item.get("cmdt_name"),
                "group":    item.get("cmdt_grp_name"),
                "price":    float(item.get("as_on_price")   or 0),
                "arrival":  float(item.get("as_on_arrival") or 0),
                "date":     item.get("reported_date"),
                "trend":    item.get("trend"),
                "state":    item.get("state_name"),
                "district": item.get("dist_name"),
                "market":   item.get("mkt_name"),
                "min_price":float(item.get("min_price") or 0),
                "max_price":float(item.get("max_price") or 0),
            }
            all_records.append(cleaned)

    return all_records

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    ses = curl_requests.Session()

    now       = datetime.now()
    date_str  = now.strftime("%Y-%m-%d")
    date_disp = now.strftime("%d-%m-%Y")
    hour      = now.hour

    print(f"Fetching data for {date_str} (hour {hour}) …")
    records = fetch_all_records(ses, date_str)

    # ── Encode payload ────────────────────────────────────────────────────────
    raw_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    xor_key  = make_xor_key(date_str, hour)
    encoded  = xor_encode(raw_json, xor_key)

    # ── Signature ─────────────────────────────────────────────────────────────
    sig = make_sig(date_str, hour)

    # ── Decoy noise (convincing-looking but meaningless) ──────────────────────
    proverb = random.choice(PROVERBS)
    noise_layers = {
        "alpha": base64.b64encode(random.randbytes(24)).decode(),
        "beta":  "".join(random.choices("0123456789abcdef", k=32)),
        "gamma": random.choice(QUALITY_CODES),
        "delta": random.choice(SEASON_TAGS),
    }

    output = {
        # ── Real metadata (used by decoder) ──
        "_v":   3,
        "_ts":  now.isoformat(),
        "_h":   hour,
        "_d":   date_disp,
        "_sig": sig,
        "_c":   len(records),
        "payload": encoded,
        # ── Cultural layer ───────────────────
        "_proverb": proverb,
        "_season":  random.choice(SEASON_TAGS),
        # ── Noise / decoys ───────────────────
        "_n":   noise_layers,
        "_ref": "உழவர் நம்பன் | Ulavarnanban",
        "_enc": "xor-b64-v3",
    }

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅  prices.json saved  →  {len(records)} records  |  sig={sig[:8]}…")

if __name__ == "__main__":
    main()
