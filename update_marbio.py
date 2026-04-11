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

# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------

def normalize(text):
    """Lowercase, remove punctuation, split into word set."""
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    return set(text.split())

def similarity(a, b):
    """Jaccard similarity between two texts (0-1)."""
    wa, wb = normalize(a), normalize(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

def is_duplicate(new_article, existing_articles, url_set, title_threshold=0.6, content_threshold=0.45):
    """
    Check if a new article is a duplicate based on:
    1. Exact URL match
    2. Title similarity above threshold
    3. Content similarity above threshold
    """
    new_url = new_article.get("url", "").rstrip("/").lower()
    new_title = new_article.get("title", "")
    new_content = new_article.get("content", "")

    # 1. URL match
    if new_url and new_url in url_set:
        return True, "same URL"

    for existing in existing_articles:
        ex_title = existing.get("title", "")
        ex_content = existing.get("content", "")

        # 2. Title similarity
        ts = similarity(new_title, ex_title)
        if ts > title_threshold:
            return True, f"similar title ({ts:.0%}): '{ex_title[:60]}'"

        # 3. Content similarity
        cs = similarity(new_content, ex_content)
        if cs > content_threshold:
            return True, f"similar content ({cs:.0%}): '{ex_title[:60]}'"

    return False, ""

# ---------------------------------------------------------------------------
# Tavily search — with recency filter
# ---------------------------------------------------------------------------

def tavily_search(query):
    try:
        r = requests.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5,
            "days": 3,                       # <-- only results from last 3 days
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
        r = []
        for q in queries:
            print(f"    {q}")
            r.extend(tavily_search(q))
        results[cat] = r
        print(f"    Found {len(r)} results")
    return results

# ---------------------------------------------------------------------------
# Claude generation — improved prompt
# ---------------------------------------------------------------------------

def call_claude(search_results, existing_articles_by_cat):
    today = date.today().isoformat()

    # Build a compact summary of existing articles (titles + first 80 chars of content)
    existing_summary = {}
    for cat, arts in existing_articles_by_cat.items():
        existing_summary[cat] = [
            {"title": a.get("title",""), "content_preview": a.get("content","")[:100]}
            for a in arts[:8]  # last 8 per category to keep prompt manageable
        ]

    prompt = f"""You are the editor of Marbio News, a daily health watch bulletin.
Your job is to write 2-3 NEW articles per category from today's search results.

CRITICAL RULES TO AVOID REPETITION:
1. Each article must cover a genuinely NEW event, announcement, data point, or development.
2. Do NOT rephrase or repackage an existing article with a different title.
3. If a search result covers the same topic as an existing article, SKIP IT — even if the wording is different.
4. If you cannot find enough genuinely new material for a category, return FEWER articles (even 0 is acceptable). Quality over quantity.
5. Compare your draft against the EXISTING ARTICLES below. If the core information is already covered, do not include it.

SEARCH RESULTS:
{json.dumps(search_results, indent=2, ensure_ascii=False)[:12000]}

EXISTING ARTICLES (recent, by category — do NOT repeat these topics):
{json.dumps(existing_summary, indent=2, ensure_ascii=False)[:6000]}

TODAY: {today}

For each article you decide to keep:
- title: short factual title in the source language
- url: exact source URL from the search results
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

If a category has no genuinely new content, use an empty array [].
IMPORTANT: Use simple ASCII characters. Each summary must be self-contained and informative."""

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

# ---------------------------------------------------------------------------
# HTML parsing & rebuilding (unchanged)
# ---------------------------------------------------------------------------

def extract_data(html):
    m = re.search(r'(?:let|var) articlesData=(\{.*?\});', html, re.DOTALL)
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
    """Return flat list of all articles across categories."""
    all_arts = []
    for arts in data.values():
        all_arts.extend(arts)
    return all_arts

def get_url_set(data):
    """Return set of normalized URLs from existing data."""
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
    months = {1:"janvier",2:"fevrier",3:"mars",4:"avril",5:"mai",6:"juin",7:"juillet",8:"aout",9:"septembre",10:"octobre",11:"novembre",12:"decembre"}
    d = f"{datetime.now().day} {months[datetime.now().month]} {datetime.now().year}"
    return re.sub(r'Mis à jour le \d+ \w+ \d{4}', f'Mis à jour le {d}', html)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("="*50)
    print("Marbio News - Daily Update (v2 — dedup)")
    print("="*50)

    print("\nReading index.html...")
    with open("index.html","r",encoding="utf-8") as f:
        html = f.read()

    print("Extracting articles...")
    data = extract_data(html)
    if not data:
        print("FATAL: Could not parse")
        return

    all_existing = get_all_articles(data)
    url_set = get_url_set(data)
    print(f"Found {len(all_existing)} existing articles, {len(url_set)} unique URLs")

    print("\nSearching with Tavily (last 3 days only)...")
    results = search_all()

    print("\nGenerating with Claude (enhanced dedup prompt)...")
    new = call_claude(results, data)
    if not new:
        print("ERROR: No articles generated")
        return

    print("\nMerging with similarity check...")
    total_added = 0
    total_rejected = 0
    for cat, arts in new.items():
        if cat not in data or not isinstance(arts, list):
            continue
        added = 0
        for a in arts:
            dup, reason = is_duplicate(a, all_existing, url_set)
            if dup:
                print(f"  SKIP [{cat}] '{a.get('title','')[:50]}' — {reason}")
                total_rejected += 1
            else:
                data[cat].insert(0, a)
                all_existing.append(a)       # add to pool so next articles are checked against it too
                new_url = a.get("url","").rstrip("/").lower()
                if new_url:
                    url_set.add(new_url)
                added += 1
                total_added += 1
        print(f"  {cat}: +{added} added")

    print(f"\nTotal: +{total_added} added, {total_rejected} rejected as duplicates")

    if total_added == 0:
        print("Nothing genuinely new today.")
        return

    print("\nUpdating index.html...")
    new_js = rebuild_js(data)
    html = re.sub(r'(?:let|var) articlesData=\{.*?\};', new_js, html, flags=re.DOTALL)
    html = update_footer(html)

    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)
    print(f"\nDone! {total_added} genuinely new articles added.")

if __name__ == "__main__":
    main()
