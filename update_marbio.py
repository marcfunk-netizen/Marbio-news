import os, json, re, requests
from datetime import datetime, date

TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

CATEGORIES = {
    "african-cdc": [
        "Africa CDC news 2026",
        "Africa CDC outbreak response surveillance",
    ],
    "african-medical-agency": [
        "African Medicines Agency AMA regulation 2026",
        "AMA pharmaceutical harmonization Africa drug approval",
    ],
    "manufacture-vaccins": [
        "Africa vaccine manufacturing local production 2026",
        "PAVM AVMI vaccine factory biologics Africa",
    ],
    "unicef-gavi": [
        "Gavi vaccine alliance funding 2026",
        "UNICEF immunization campaign cholera malaria polio",
    ],
    "sante-maroc": [
        "Maroc sante publique hopital 2026",
        "Maroc AMO RAMED reforme sanitaire medicaments",
        "Morocco health ministry reform 2026",
    ],
    "vaccins-monde": [
        "WHO vaccine approval clinical trial 2026",
        "new vaccine development global rollout 2026",
        "mpox measles polio vaccine world 2026",
    ],
}

# ---------------------------------------------------------------------------
# Category identity keywords
# Each category has keywords that DEFINE it. If an article matches these
# keywords, it BELONGS to that category and should be BLOCKED from others.
# ---------------------------------------------------------------------------

CATEGORY_IDENTITY = {
    "african-cdc": ["africa cdc", "africacdc", "africa-cdc", "african centres for disease control"],
    "african-medical-agency": ["african medicines agency", "ama regulation", "ama harmonization", "ama operationali"],
    "manufacture-vaccins": ["vaccine manufacturing", "local production", "avmi", "pavm", "manufacturing capacity", "fabrication locale", "production locale"],
    "unicef-gavi": ["gavi", "unicef"],
    "sante-maroc": ["maroc", "morocco", "marocain", "moroccan", "ramed", "amo maroc", "tarkhiss"],
    "vaccins-monde": [],  # catch-all for global vaccine news, no exclusive keywords
}

# ---------------------------------------------------------------------------
# Cross-category contamination detection
# ---------------------------------------------------------------------------

def get_article_identity(text):
    """Return set of category keys that this text primarily belongs to."""
    text_lower = text.lower()
    matches = set()
    for cat, keywords in CATEGORY_IDENTITY.items():
        for kw in keywords:
            if kw in text_lower:
                matches.add(cat)
                break
    return matches

def is_wrong_category(article, target_category):
    """
    Check if an article is contamination from another category.
    Returns True if the article's PRIMARY identity belongs to a different category.
    """
    title = article.get("title", "")
    content = article.get("content", "")
    url = article.get("url", "")
    combined = title + " " + content + " " + url

    identities = get_article_identity(combined)

    # If no strong identity detected, it's fine wherever Claude put it
    if not identities:
        return False

    # If it matches the target category, it's fine
    if target_category in identities:
        return False

    # It matches OTHER categories but NOT the target — it's contamination
    return True

def filter_tavily_results(results, target_category):
    """Remove Tavily results that clearly belong to other categories."""
    filtered = []
    removed = 0
    for r in results:
        combined = (r.get("url", "") + " " + r.get("title", "") + " " + (r.get("content", "") or r.get("snippet", ""))[:300]).lower()
        identities = get_article_identity(combined)

        # Keep if: no strong identity, or matches target category
        if not identities or target_category in identities:
            filtered.append(r)
        else:
            removed += 1

    return filtered, removed

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

def is_duplicate(new_article, existing_articles, url_set, title_threshold=0.6, content_threshold=0.45):
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
# Tavily search
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
            print(f"    {q}")
            raw.extend(tavily_search(q))

        # Pre-filter: remove results that belong to other categories
        filtered, removed = filter_tavily_results(raw, cat)
        if removed:
            print(f"    Filtered out {removed} cross-category results")

        results[cat] = filtered
        print(f"    Kept {len(filtered)} results")
    return results

# ---------------------------------------------------------------------------
# Claude generation
# ---------------------------------------------------------------------------

CATEGORY_RULES = """
STRICT CATEGORY RULES — each article must belong to its category based on its PRIMARY subject:
- "african-cdc": ONLY about Africa CDC as an institution (strategy, leadership, partnerships, data systems).
- "african-medical-agency": ONLY about AMA, drug regulation, pharmaceutical harmonization.
- "manufacture-vaccins": ONLY about vaccine/medicine MANUFACTURING and PRODUCTION (factories, workforce, technology transfer).
- "unicef-gavi": ONLY about UNICEF and/or Gavi activities (funding, procurement, immunization campaigns).
- "sante-maroc": ONLY about MOROCCO's health system specifically (hospitals, reforms, medicines, Moroccan policy).
- "vaccins-monde": ONLY about vaccine development, clinical trials, approvals, global campaigns (WHO, diseases, new vaccines).

CRITICAL:
1. An article about Africa CDC does NOT go in sante-maroc, vaccins-monde, unicef-gavi, or manufacture-vaccins.
2. An article about Gavi/UNICEF does NOT go in vaccins-monde or african-cdc.
3. An article about AMA does NOT go in african-cdc or manufacture-vaccins.
4. Do NOT reframe an article from one domain to fit another category.
5. If a topic was already covered in ANY category, do NOT repeat it anywhere.
6. If no genuinely new content exists for a category, return an empty array.
"""

def call_claude(search_results, existing_articles_by_cat):
    today = date.today().isoformat()

    all_recent = []
    for cat, arts in existing_articles_by_cat.items():
        for a in arts[:8]:
            all_recent.append({
                "category": cat,
                "title": a.get("title", ""),
                "content_preview": a.get("content", "")[:120],
            })

    prompt = f"""You are the editor of Marbio News, a daily health watch bulletin.
Your job is to write 2-3 NEW articles per category from today's search results.

{CATEGORY_RULES}

RULES TO AVOID REPETITION:
1. Each article must cover a genuinely NEW event, announcement, or data point.
2. Do NOT rephrase or repackage an existing article with a different title.
3. If a topic has ALREADY been covered in ANY category below, do NOT write about it again — even from a different angle or in a different category.
4. If you cannot find enough genuinely new material for a category, return FEWER articles (even 0 is fine). Quality over quantity.

SEARCH RESULTS (by category):
{json.dumps(search_results, indent=2, ensure_ascii=False)[:12000]}

ALL EXISTING ARTICLES (across ALL categories — do NOT repeat any of these topics in ANY category):
{json.dumps(all_recent, indent=2, ensure_ascii=False)[:8000]}

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
    print("Marbio News - Daily Update (v5 — full cross-category filter)")
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

    print("\nSearching with Tavily (last 3 days, cross-category filtered)...")
    results = search_all()

    print("\nGenerating with Claude...")
    new = call_claude(results, data)
    if not new:
        print("ERROR: No articles generated")
        return

    print("\nMerging with cross-category dedup + identity check...")
    total_added = 0
    total_rejected = 0
    total_wrong_cat = 0
    for cat, arts in new.items():
        if cat not in data or not isinstance(arts, list):
            continue
        added = 0
        for a in arts:
            # Check 1: article belongs to a different category
            if is_wrong_category(a, cat):
                print(f"  BLOCK [{cat}] '{a.get('title','')[:50]}' -- belongs to another category")
                total_wrong_cat += 1
                continue

            # Check 2: duplicate detection across all categories
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

    print(f"\nTotal: +{total_added} added, {total_rejected} duplicates, {total_wrong_cat} wrong-category blocked")

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
