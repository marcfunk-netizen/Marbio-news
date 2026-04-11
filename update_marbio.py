import os, json, re, requests
from datetime import datetime, date

TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# ---------------------------------------------------------------------------
# Search queries per category — designed to find category-specific sources
# ---------------------------------------------------------------------------

CATEGORIES = {
    "african-cdc": [
        "Africa CDC news april 2026",
        "Africa CDC outbreak surveillance strategy 2026",
    ],
    "african-medical-agency": [
        "African Medicines Agency AMA regulation 2026",
        "pharmaceutical harmonization Africa drug approval 2026",
    ],
    "manufacture-vaccins": [
        "vaccine manufacturing plant Africa 2026",
        "Aspen BioVac Senegal Institut Pasteur Dakar vaccine production",
    ],
    "unicef-gavi": [
        "Gavi vaccine funding 2026",
        "UNICEF immunization campaign Africa 2026",
    ],
    "sante-maroc": [
        "Maroc sante publique actualite 2026",
        "Morocco health reform hospital ministry 2026",
        "reforme sanitaire Maroc medicaments 2026",
    ],
    "vaccins-monde": [
        "WHO vaccine approval 2026",
        "new vaccine clinical trial results 2026",
        "global immunization campaign measles polio 2026",
    ],
}

# ---------------------------------------------------------------------------
# Source domain routing
# Results from these domains are ONLY allowed in specific categories.
# If a domain is not listed, the result is allowed anywhere.
# ---------------------------------------------------------------------------

DOMAIN_CATEGORY_MAP = {
    "africacdc.org":        ["african-cdc"],
    "au.int":               ["african-cdc"],
    "nepad.org":            ["african-medical-agency", "african-cdc"],
    "tmda.go.tz":           ["african-medical-agency"],
    "gavi.org":             ["unicef-gavi"],
    "unicef.org":           ["unicef-gavi"],
    # Morocco-specific sources — only in sante-maroc
    "sante.gov.ma":         ["sante-maroc"],
    "maroc-hebdo.com":      ["sante-maroc"],
    "santemag.ma":          ["sante-maroc"],
    "hespress.com":         ["sante-maroc"],
    "africa24tv.com":       ["sante-maroc"],
    "medias24.com":         ["sante-maroc"],
    "le360.ma":             ["sante-maroc"],
    "lavieeco.com":         ["sante-maroc"],
    # WHO — allowed in vaccins-monde and unicef-gavi
    "who.int":              ["vaccins-monde", "unicef-gavi"],
}

def get_domain(url):
    """Extract root domain from URL."""
    try:
        host = re.sub(r'^www\.', '', requests.utils.urlparse(url).hostname or '')
        return host
    except:
        return ""

def is_domain_allowed(url, target_category):
    """Check if a URL's domain is allowed in the target category."""
    domain = get_domain(url)
    for restricted_domain, allowed_cats in DOMAIN_CATEGORY_MAP.items():
        if restricted_domain in domain:
            return target_category in allowed_cats
    # Domain not in restriction map — allowed anywhere
    return True

# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------

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
        ex_title = existing.get("title", "")
        ex_content = existing.get("content", "")

        ts = similarity(new_title, ex_title)
        if ts > title_threshold:
            return True, f"similar title ({ts:.0%}): '{ex_title[:60]}'"

        cs = similarity(new_content, ex_content)
        if cs > content_threshold:
            return True, f"similar content ({cs:.0%}): '{ex_title[:60]}'"

    return False, ""

# ---------------------------------------------------------------------------
# Tavily search — with domain filtering
# ---------------------------------------------------------------------------

def tavily_search(query):
    try:
        r = requests.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5,
            "days": 3,
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

        # Filter out results whose source domain doesn't belong to this category
        filtered = []
        removed = 0
        for r in raw:
            url = r.get("url", "")
            if is_domain_allowed(url, cat):
                filtered.append(r)
            else:
                domain = get_domain(url)
                print(f"    FILTERED: {domain} not allowed in {cat}")
                removed += 1

        results[cat] = filtered
        print(f"    Kept {len(filtered)} results ({removed} filtered out)")
    return results

# ---------------------------------------------------------------------------
# Claude generation
# ---------------------------------------------------------------------------

def call_claude(search_results, existing_articles_by_cat):
    today = date.today().isoformat()

    # Flat list of ALL recent articles for cross-category dedup
    all_recent = []
    for cat, arts in existing_articles_by_cat.items():
        for a in arts[:10]:
            all_recent.append({
                "category": cat,
                "title": a.get("title", ""),
                "content_preview": a.get("content", "")[:150],
            })

    prompt = f"""You are the editor of Marbio News, a daily health watch bulletin.
Write 2-3 NEW articles per category from today's search results.

STRICT CATEGORY RULES:
- "african-cdc": ONLY about Africa CDC as an institution.
- "african-medical-agency": ONLY about AMA and drug regulation.
- "manufacture-vaccins": ONLY about vaccine/medicine MANUFACTURING (factories, production lines, workforce training for manufacturing).
- "unicef-gavi": ONLY about UNICEF and/or Gavi activities.
- "sante-maroc": ONLY about Morocco's health system. Articles must be primarily about Moroccan policy, hospitals, reforms, or public health in Morocco.
- "vaccins-monde": ONLY about vaccine R&D, clinical trials, WHO campaigns, global immunization. NOT about Africa CDC.

ABSOLUTE RULES:
1. NEVER put Africa CDC institutional news in any category other than "african-cdc".
2. NEVER reframe a source article to fit a different category. If the source is about Africa CDC, it goes ONLY in "african-cdc".
3. Each article's URL must come from the search results provided for THAT category.
4. Do NOT use a URL from one category's search results in a different category.
5. If a topic appears in EXISTING ARTICLES below (in ANY category), do NOT write about it again.
6. If no genuinely new content exists for a category, return an empty array [].
7. Quality over quantity: 0 articles is better than recycled content.

SEARCH RESULTS (by category — use ONLY within the assigned category):
{json.dumps(search_results, indent=2, ensure_ascii=False)[:12000]}

ALL EXISTING ARTICLES (do NOT repeat ANY of these topics):
{json.dumps(all_recent, indent=2, ensure_ascii=False)[:8000]}

TODAY: {today}

For each article:
- title: short factual title in the source language
- url: exact source URL from the search results FOR THAT CATEGORY
- content: 3-5 sentence summary with key figures. In source language.
- date: "{today}"

Reply with ONLY valid JSON. No markdown, no backticks:
{{
  "african-cdc": [{{"title":"...","url":"...","content":"...","date":"{today}"}}],
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
                cleaned = re.sub(r',\s*([}\]])', r'\1', m.group(0))
                return json.loads(cleaned)
    except Exception as e:
        print(f"Claude error: {e}")
    return None

# ---------------------------------------------------------------------------
# Post-generation validation: check URL belongs to category
# ---------------------------------------------------------------------------

def validate_article_category(article, category):
    """Final check: is the article's URL allowed in this category?"""
    url = article.get("url", "")
    if not url:
        return False, "no URL"
    if not is_domain_allowed(url, category):
        domain = get_domain(url)
        return False, f"domain {domain} not allowed in {category}"
    return True, ""

# ---------------------------------------------------------------------------
# HTML parsing & rebuilding
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
    months = {1:"janvier",2:"fevrier",3:"mars",4:"avril",5:"mai",6:"juin",7:"juillet",8:"aout",9:"septembre",10:"octobre",11:"novembre",12:"decembre"}
    d = f"{datetime.now().day} {months[datetime.now().month]} {datetime.now().year}"
    return re.sub(r'Mis à jour le \d+ \w+ \d{4}', f'Mis à jour le {d}', html)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("="*50)
    print("Marbio News - Daily Update (v6 — domain routing)")
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

    print("\nSearching with Tavily (domain-filtered)...")
    results = search_all()

    # Log how many results per category after filtering
    for cat, res in results.items():
        if not res:
            print(f"  WARNING: {cat} has 0 results after filtering")

    print("\nGenerating with Claude...")
    new = call_claude(results, data)
    if not new:
        print("ERROR: No articles generated")
        return

    print("\nMerging with triple validation...")
    total_added = 0
    total_rejected = 0
    total_wrong_domain = 0
    for cat, arts in new.items():
        if cat not in data or not isinstance(arts, list):
            continue
        added = 0
        for a in arts:
            # Check 1: URL domain belongs to this category
            valid, reason = validate_article_category(a, cat)
            if not valid:
                print(f"  BLOCK [{cat}] '{a.get('title','')[:50]}' -- {reason}")
                total_wrong_domain += 1
                continue

            # Check 2: duplicate detection across ALL categories
            dup, reason = is_duplicate(a, all_existing, url_set)
            if dup:
                print(f"  SKIP [{cat}] '{a.get('title','')[:50]}' -- {reason}")
                total_rejected += 1
            else:
                data[cat].insert(0, a)
                all_existing.append(a)
                new_url = a.get("url","").rstrip("/").lower()
                if new_url:
                    url_set.add(new_url)
                added += 1
                total_added += 1
        print(f"  {cat}: +{added} added")

    print(f"\nTotal: +{total_added} added, {total_rejected} duplicates, {total_wrong_domain} wrong-domain blocked")

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
