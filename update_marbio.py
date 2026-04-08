import os, json, re, requests
from datetime import datetime, date

TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

CATEGORIES = {
    "african-cdc": ["Africa CDC latest news 2026", "Africa CDC health security continental strategy"],
    "african-medical-agency": ["African Medicines Agency AMA regulation news 2026", "AMA pharmaceutical harmonization Africa"],
    "manufacture-vaccins": ["Africa vaccine manufacturing local production 2026", "PAVM AVMI vaccine workforce Africa"],
    "unicef-gavi": ["Gavi vaccines Africa campaign 2026", "UNICEF immunization Africa cholera malaria"],
    "sante-maroc": ["sante publique Maroc 2026 actualites", "ministere sante Maroc reforme hopitaux"],
    "vaccins-monde": ["WHO vaccination campaign 2026", "global vaccine clinical trial approval 2026"],
}

def tavily_search(query):
    try:
        r = requests.post("https://api.tavily.com/search", json={"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced", "max_results": 5}, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"  Tavily error: {e}")
        return []

def search_all():
    results = {}
    for cat, queries in CATEGORIES.items():
        print(f"\n  Searching: {cat}")
        r = []
        for q in queries:
            print(f"    {q}")
            r.extend(tavily_search(q))
        results[cat] = r
        print(f"    Found {len(r)} results")
    return results

def call_claude(search_results, existing_titles):
    today = date.today().isoformat()
    prompt = f"""You are the editor of Marbio News. Write 2-3 new articles per category from these search results.

SEARCH RESULTS:
{json.dumps(search_results, indent=2, ensure_ascii=False)[:12000]}

EXISTING TITLES (do not duplicate):
{json.dumps(existing_titles, ensure_ascii=False)}

TODAY: {today}

For each article:
- title: short factual title in the source language
- url: exact source URL
- content: rich 3-5 sentence summary with key figures, context, impact. In source language.
- date: "{today}"

Reply with ONLY a valid JSON object. No markdown, no backticks. Format:
{{
  "african-cdc": [{{"title":"...","url":"...","content":"...","date":"{today}"}}],
  "african-medical-agency": [...],
  "manufacture-vaccins": [...],
  "unicef-gavi": [...],
  "sante-maroc": [...],
  "vaccins-monde": [...]
}}

IMPORTANT: Use simple ASCII characters. Avoid special quotes or accented characters in article content where possible. Each summary must be self-contained and informative."""

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
                cleaned = re.sub(r',\s*([}\]])', r'\1', m.group(0))
                return json.loads(cleaned)
    except Exception as e:
        print(f"Claude error: {e}")
    return None

def extract_data(html):
    m = re.search(r'let articlesData=(\{.*?\});', html, re.DOTALL)
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

def get_titles(data):
    t = []
    for arts in data.values():
        for a in arts:
            t.append(a.get("title", ""))
    return t

def rebuild_js(data):
    lines = ["let articlesData={"]
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
    months = {1:"janvier",2:"fevrier",3:"mars",4:"avril",5:"mai",6:"juin",7:"juillet",8:"aout",9:"septembre",10:"octobre",11:"novembre",12:"decembre"}
    d = f"{datetime.now().day} {months[datetime.now().month]} {datetime.now().year}"
    return re.sub(r'Mis à jour le \d+ \w+ \d{4}', f'Mis à jour le {d}', html)

def main():
    print("="*50)
    print("Marbio News - Daily Update")
    print("="*50)
    print("\nReading index.html...")
    with open("index.html","r",encoding="utf-8") as f:
        html = f.read()
    print("Extracting articles...")
    data = extract_data(html)
    if not data:
        print("FATAL: Could not parse")
        return
    titles = get_titles(data)
    print(f"Found {len(titles)} existing articles")
    print("\nSearching with Tavily...")
    results = search_all()
    print("\nGenerating with Claude...")
    new = call_claude(results, titles)
    if not new:
        print("ERROR: No articles generated")
        return
    print("\nMerging...")
    total = 0
    for cat, arts in new.items():
        if cat in data and isinstance(arts, list):
            unique = [a for a in arts if a.get("title") not in titles]
            data[cat] = unique + data[cat]
            total += len(unique)
            print(f"  {cat}: +{len(unique)}")
    print(f"\nTotal: +{total} new articles")
    if total == 0:
        print("Nothing new.")
        return
    print("\nUpdating index.html...")
    new_js = rebuild_js(data)
    html = re.sub(r'let articlesData=\{.*?\};', new_js, html, flags=re.DOTALL)
    html = update_footer(html)
    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)
    print(f"\nDone! {total} new articles added.")

if __name__ == "__main__":
    main()
