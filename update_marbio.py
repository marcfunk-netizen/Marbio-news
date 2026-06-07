```python
import os, json, re, requests
from datetime import datetime, date, timedelta

TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

TODAY = date.today().isoformat()
MONTH_YEAR = date.today().strftime("%B %Y")

CATEGORIES = {
    "african-cdc": [
        f"Africa CDC {MONTH_YEAR}",
        f"Africa CDC outbreak surveillance {MONTH_YEAR}",
    ],
    "african-medical-agency": [
        f"African Medicines Agency AMA {MONTH_YEAR}",
        f"AMA pharmaceutical regulation Africa {MONTH_YEAR}",
    ],
    "manufacture-vaccins": [
        f"vaccine manufacturing Africa {MONTH_YEAR}",
        f"Africa vaccine production CDMO {MONTH_YEAR}",
    ],
    "unicef-gavi": [
        f"Gavi UNICEF vaccine {MONTH_YEAR}",
        f"UNICEF immunization Africa {MONTH_YEAR}",
    ],
    "sante-maroc": [
        f"Maroc sante {MONTH_YEAR}",
        f"Morocco health ministry {MONTH_YEAR}",
        f"reforme sanitaire Maroc {MONTH_YEAR}",
    ],
    "vaccins-monde": [
        f"WHO vaccine {MONTH_YEAR}",
        f"vaccine clinical trial {MONTH_YEAR}",
        f"global immunization WHO {MONTH_YEAR}",
    ],
}

DOMAIN_CATEGORY_MAP = {
    "africacdc.org":        ["african-cdc"],
    "au.int":               ["african-cdc"],
    "nepad.org":            ["african-medical-agency", "african-cdc"],
    "tmda.go.tz":           ["african-medical-agency"],
    "gavi.org":             ["unicef-gavi"],
    "unicef.org":           ["unicef-gavi"],
    "sante.gov.ma":         ["sante-maroc"],
    "maroc-hebdo.com":      ["sante-maroc"],
    "santemag.ma":          ["sante-maroc"],
    "hespress.com":         ["sante-maroc"],
    "africa24tv.com":       ["sante-maroc"],
    "medias24.com":         ["sante-maroc"],
    "le360.ma":             ["sante-maroc"],
    "lavieeco.com":         ["sante-maroc"],
    "who.int":              ["vaccins-monde", "unicef-gavi"],
}

def get_domain(url):
    try:
        host = re.sub(r'^www\.', '', requests.utils.urlparse(url).hostname or '')
        return host
    except:
        return ""

def is_domain_allowed(url, target_category):
    domain = get_domain(url)
    for restricted_domain, allowed_cats in DOMAIN_CATEGORY_MAP.items():
        if restricted_domain in domain:
            return target_category in allowed_cats
    return True

def normalize(text):
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    return set(text.split())

def similarity(a, b):
    wa, wb = normalize(a), normalize(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

def is_duplicate(new_article, existing_articles, url_set, title_threshold=0.55, content_threshold=0.40):
    new_url = new_article.get("url", "").rstrip("/").lower()
    new_title = new_article.get("title", "")
    new_content = new_article.get("content", "")
    if new_url and new_url in url_set:
        return True, "same URL"
    for existing in existing_articles:
        ts = similarity(new_title, existing.get("title", ""))
        if ts > title_threshold:
            return True, f"similar title ({ts:.0%})"
        cs = similarity(new_content, existing.get("content", ""))
        if cs > content_threshold:
            return True, f"similar content ({cs:.0%})"
    return False, ""

def tavily_search(query):
    try:
        r = requests.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5,
            "days": 30,
        }, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"  Tavily error: {e}")
        return []

def search_all():
    results = {}
    for cat, queries in CATEGORIES.items():
        print(f"\n  Searching: {cat}")
        raw = []
        for q in queries:
            print(f"    query: {q}")
            raw.extend(tavily_search(q))
        filtered = []
        removed = 0
        for r in raw:
            url = r.get("url", "")
            if is_domain_allowed(url, cat):
                filtered.append(r)
            else:
                removed += 1
        results[cat] = filtered
        print(f"    Kept {len(filtered)} ({removed} filtered)")
    return results

def call_claude(search_results, existing_articles_by_cat):
    all_recent = []
    for cat, arts in existing_articles_by_cat.items():
        for a in arts[:5]:
            all_recent.append({
                "category": cat,
                "title": a.get("title", ""),
                "url": a.get("url", ""),
            })

    prompt = f"""You are the editor of Marbio News, a daily health watch bulletin.
Write 2-3 NEW articles per category from today's search results.

STRICT CATEGORY RULES:
- "african-cdc": ONLY about Africa CDC institution.
- "african-medical-agency": ONLY about AMA and drug regulation.
- "manufacture-vaccins": ONLY about vaccine/medicine MANUFACTURING.
- "unicef-gavi": ONLY about UNICEF and/or Gavi.
- "sante-maroc": ONLY about Morocco's health system.
- "vaccins-monde": ONLY about vaccine R&D, WHO campaigns, global immunization.

ABSOLUTE RULES:
1. Each article URL must come from the search results for THAT category.
2. Do NOT reuse any URL from EXISTING ARTICLES.
3. If no new content exists for a category, return [].
4. Write content in the language of the source article.

SEARCH RESULTS:
{json.dumps(search_results, indent=2, ensure_ascii=False)[:12000]}

EXISTING ARTICLES URLS (do NOT reuse these):
{json.dumps([a["url"] for a in all_recent], indent=2)[:4000]}

TODAY: {TODAY}

Reply with ONLY valid JSON:
{{
  "african-cdc": [{{"title":"...","url":"...","content":"...","date":"{TODAY}"}}],
  "african-medical-agency": [...],
  "manufacture-vaccins": [...],
  "unicef-gavi": [...],
  "sante-maroc": [...],
  "vaccins-monde": [...]
}}"""

    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": 8000, "messages": [{"role": "user", "content": prompt}]},
            timeout=120)
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        text = re.sub(r"^```json\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())
        text = re.sub(r',\s*([}\]])', r'\1', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                return json.loads(re.sub(r',\s*([}\]])', r'\1', m.group(0)))
    except Exception as e:
        print(f"Claude error: {e}")
    return None

def extract_data(html):
    m = re.search(r'var articlesData=(\{.*?\});', html, re.DOTALL)
    if not m:
        print("ERROR: articlesData not found")
        return None
    js = m.group(1)
    js = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r' "\1":', js)
    js = re.sub(r',\s*([}\]])', r'\1', js)
    try:
        return json.loads(js)
    except json.JSONDecodeError as e:
        print(f"Parse error: {e}")
        return None

def get_all_articles(data):
    all_arts = []
    for arts in data.values():
        all_arts.extend(arts)
    return all_arts

def get_url_set(data):
    urls = set()
    for arts in data.values():
        for a in arts:
            url = a.get("url", "").rstrip("/").lower()
            if url:
                urls.add(url)
    return urls

def rebuild_js(data):
    lines = ["var articlesData={"]
    for cat in data:
        lines.append('"' + cat + '":[')
        for a in data[cat]:
            t = a.get("title","").replace('\\','\\\\').replace('"','\\"').replace('\n',' ').replace('\r','')
            u = a.get("url","").replace('"','\\"')
            c = a.get("content","").replace('\\','\\\\').replace('"','\\"').replace('\n',' ').replace('\r','').replace('\t',' ')
            d = a.get("date","")
            lines.append('{' + '"title":"'+t+'","url":"'+u+'","content":"'+c+'","date":"'+d+'"' + '},')
        lines.append("],")
    lines.append("};")
    return "\n".join(lines)

def update_footer(html):
    months = {1:"janvier",2:"février",3:"mars",4:"avril",5:"mai",6:"juin",
              7:"juillet",8:"août",9:"septembre",10:"octobre",11:"novembre",12:"décembre"}
    d = f"{datetime.now().day} {months[datetime.now().month]} {datetime.now().year}"
    return re.sub(r'Mis à jour le \d+ \w+ \d{4}', f'Mis à jour le {d}', html)

def main():
    print("="*50)
    print(f"Marbio News - Daily Update - {TODAY}")
    print("="*50)

    with open("index.html","r",encoding="utf-8") as f:
        html = f.read()

    data = extract_data(html)
    if not data:
        print("FATAL: Could not parse index.html")
        return

    all_existing = get_all_articles(data)
    url_set = get_url_set(data)
    print(f"Found {len(all_existing)} existing articles")

    results = search_all()

    print("\nGenerating with Claude...")
    new = call_claude(results, data)
    if not new:
        print("ERROR: No articles generated")
        return

    print("\nMerging...")
    total_added = 0
    for cat, arts in new.items():
        if cat not in data or not isinstance(arts, list):
            continue
        added = 0
        for a in arts:
            if not is_domain_allowed(a.get("url",""), cat):
                print(f"  BLOCK [{cat}] wrong domain")
                continue
            dup, reason = is_duplicate(a, all_existing, url_set)
            if dup:
                print(f"  SKIP [{cat}] {reason}")
            else:
                data[cat].insert(0, a)
                all_existing.append(a)
                url_set.add(a.get("url","").rstrip("/").lower())
                added += 1
                total_added += 1
        print(f"  {cat}: +{added}")

    print(f"\nTotal: +{total_added} new articles")

    if total_added == 0:
        print("Nothing new today.")
        return

    new_js = rebuild_js(data)
    html = re.sub(r'var articlesData=\{.*?\};', new_js, html, flags=re.DOTALL)
    html = update_footer(html)

    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)
    print(f"Done! index.html updated.")

if __name__ == "__main__":
    main()
```

L'unique différence avec ton fichier actuel : **toutes les queries de la deuxième ligne de chaque catégorie ont maintenant `{MONTH_YEAR}` au lieu de `"2026"` hardcodé.** C'est tout.
