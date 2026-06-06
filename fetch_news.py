import json, os, urllib.request

API_KEY = os.environ["TAVILY_API_KEY"]
URL = "https://api.tavily.com/search"

QUERIES = {
    "african-cdc":   "Africa CDC 2026",
    "ama":           "African Medicines Agency AMA 2026",
    "manufacture":   "vaccine manufacturing Africa 2026",
    "unicef-gavi":   "UNICEF GAVI vaccine Africa 2026",
    "sante-maroc":   "sante Maroc vaccins 2026",
    "vaccins-monde": "WHO vaccine news 2026",
}

result = {}
for cat_id, query in QUERIES.items():
    payload = json.dumps({
        "api_key": API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": 8,
        "include_answer": False,
        "include_raw_content": False,
        "days": 14,
    }).encode()
    req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        articles = []
        for item in data.get("results", []):
            articles.append({
                "title":   item.get("title", ""),
                "url":     item.get("url", ""),
                "content": item.get("content", ""),
                "date":    item.get("published_date", ""),
            })
        result[cat_id] = articles
        print(f"OK {cat_id}: {len(articles)} articles")
    except Exception as e:
        print(f"ERR {cat_id}: {e}")
        result[cat_id] = []

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("data.json written.")
