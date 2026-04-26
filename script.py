import json
from curl_cffi import requests as curl_requests

ses = curl_requests.Session()

url = "https://api.agmarknet.gov.in/v1/dashboard-data/"

headers = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
}

base_payload = {
    'dashboard': 'marketwise_price_arrival',
    'date': '2026-04-25',
    'group': [100000],
    'commodity': [100001],
    'variety': 100021,
    'state': 100006,
    'grades': [4],
    'limit': 30,
    'format': 'json',
}

response = ses.post(url, headers=headers, json=base_payload)
data = response.json()

total_pages = data['pagination']['total_pages']
#print("Total Pages:", total_pages)
all_records = []

for page in range(1, total_pages + 1):
    payload = base_payload.copy()
    payload['page'] = page

    res = ses.post(url, headers=headers, json=payload)

    if res.status_code != 200:
        print("Error at page:", page)
        break

    page_data = res.json()
    records = page_data['data']['records']

    #print(f"Fetched Page {page} → {len(records)} records")

    for item in records:
        cleaned = {
            "crop": item.get("cmdt_name"),
            "group": item.get("cmdt_grp_name"),
            "price": float(item.get("as_on_price") or 0),
            "arrival": float(item.get("as_on_arrival") or 0),
            "date": item.get("reported_date"),
            "trend": item.get("trend"),
        }
        all_records.append(cleaned)

with open("prices.json", "w") as f:
    json.dump(all_records, f, indent=2)

# print("Final data saved: prices.json")
# print("Total records:", len(all_records))
