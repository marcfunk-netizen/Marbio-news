import json, os, urllib.request

API_KEY = os.environ["TAVILY_API_KEY"]
URL = "https://api.tavily.com/search"

QUERIES = {
    "african-cdc":   "Africa CDC vaccine health news 2025",
    "ama":           "African Medicines Agency AMA regulatory news",
    "manufacture":   "vaccine manufacturing Africa biologics production",
    "unicef-gavi":   "UNICEF GAVI immunization campaign Africa",
    "sante-maroc":   "sante Maroc vaccins systeme soins 2025",
    "vaccins-monde": "vaccine global news WHO 2025",
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
