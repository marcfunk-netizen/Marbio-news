#!/usr/bin/env python3
"""
Marbio News — Daily updater
Uses Tavily API for search + Claude API for article writing
Updates articlesData in index.html
"""

import os
import json
import re
import requests
from datetime import datetime, date

TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

CATEGORIES = {
    "african-cdc": [
        "Africa CDC latest news 2026",
        "Africa CDC health security continental strategy"
    ],
    "african-medical-agency": [
        "African Medicines Agency AMA regulation news 2026",
        "AMA pharmaceutical harmonization Africa"
    ],
    "manufacture-vaccins": [
        "Africa vaccine manufacturing local production 2026",
        "PAVM AVMI vaccine workforce Africa"
    ],
    "unicef-gavi": [
        "Gavi vaccines Africa campaign 2026",
        "UNICEF immunization Africa cholera malaria"
    ],
    "sante-maroc": [
        "santé publique Maroc 2026 actualités",
        "ministère santé Maroc réforme hôpitaux"
    ],
    "vaccins-monde": [
        "WHO vaccination campaign 2026",
        "global vaccine clinical trial approval 2026"
    ],
}

def tavily_search(query):
    """Search using Tavily API"""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "max_results": 5,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"  Tavily error for '{query}': {e}")
        return []

def search_all_categories():
    """Run Tavily searches for all categories"""
    all_results = {}
    for cat_id, queries in CATEGORIES.items():
        print(f"\n🔍 Searching: {cat_id}")
        results = []
        for q in queries:
            print(f"  → {q}")
            results.extend(tavily_search(q))
        all_results[cat_id] = results
        print(f"  Found {len(results)} results")
    return all_results

def generate_articles_with_claude(search_results, existing_titles):
    """Use Claude API to write articles from search results"""
    
    prompt = f"""Tu es l'éditeur de Marbio News. Voici les résultats de recherche pour 6 catégories.

Pour CHAQUE catégorie, rédige 2-3 nouveaux articles au format JSON. 

RÉSULTATS DE RECHERCHE :
{json.dumps(search_results, indent=2, ensure_ascii=False)[:12000]}

TITRES EXISTANTS (ne pas dupliquer) :
{json.dumps(existing_titles, ensure_ascii=False)}

DATE DU JOUR : {date.today().isoformat()}

Pour chaque article :
- title : titre court et factuel, dans la langue de la source
- url : URL exacte de la source
- content : résumé RICHE de 3-5 phrases avec chiffres clés, contexte, impact. Dans la langue de la source.
- date : "{date.today().isoformat()}"

Réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans backticks, sans explication. Format exact :
{{
  "african-cdc": [
    {{"title": "...", "url": "...", "content": "...", "date": "{date.today().isoformat()}"}},
  ],
  "african-medical-agency": [...],
  "manufacture-vaccins": [...],
  "unicef-gavi": [...],
  "sante-maroc": [...],
  "vaccins-monde": [...]
}}

QUALITÉ :
- Résumés informatifs et autonomes
- Données chiffrées quand disponibles
- Sujets variés par catégorie
- Pas de doublons avec les titres existants"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        text = data["content"][0]["text"]
        # Clean potential markdown fences
        text = re.sub(r"^```json\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())
        return json.loads(text)
    except Exception as e:
        print(f"Claude API error: {e}")
        return None

def extract_articles_data(html):
    """Extract the articlesData JS object from index.html"""
    match = re.search(r'let articlesData=(\{.*?\});', html, re.DOTALL)
    if not match:
        print("ERROR: Could not find articlesData in index.html")
        return None
    
    js_obj = match.group(1)
    # Convert JS object to valid JSON
    # Add quotes around keys
    js_obj = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r' "\1":', js_obj)
    # Fix trailing commas before ] or }
    js_obj = re.sub(r',\s*([}\]])', r'\1', js_obj)
    
    try:
        return json.loads(js_obj)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        return None

def get_existing_titles(articles_data):
    """Get all existing article titles to avoid duplicates"""
    titles = []
    for cat_articles in articles_data.values():
        for article in cat_articles:
            titles.append(article.get("title", ""))
    return titles

def rebuild_articles_js(articles_data):
    """Convert articles data back to JS object format"""
    lines = []
    lines.append("let articlesData={")
    
    cats = list(articles_data.keys())
    for i, cat in enumerate(cats):
        lines.append(f'"{cat}":[')
        articles = articles_data[cat]
        for j, a in enumerate(articles):
            title = a["title"].replace('"', '\\"')
            url = a["url"].replace('"', '\\"')
            content = a["content"].replace('"', '\\"')
            date_str = a.get("date", "")
            comma = "," if j < len(articles) - 1 else ","
            lines.append(f'{{{{"title":"{title}","url":"{url}","content":"{content}","date":"{date_str}"}}}}{comma}')
        comma = "," if i < len(cats) - 1 else ","
        lines.append(f"]{comma}")
    
    lines.append("};")
    return "\n".join(lines)

def update_footer_date(html):
    """Update the footer date"""
    today_fr = datetime.now().strftime("%-d ")
    months_fr = {1:"janvier",2:"février",3:"mars",4:"avril",5:"mai",6:"juin",
                 7:"juillet",8:"août",9:"septembre",10:"octobre",11:"novembre",12:"décembre"}
    month = months_fr[datetime.now().month]
    year = datetime.now().year
    date_str = f"{datetime.now().day} {month} {year}"
    
    html = re.sub(
        r'Mis à jour le \d+ \w+ \d{4}',
        f'Mis à jour le {date_str}',
        html
    )
    return html

def main():
    print("=" * 50)
    print("📰 Marbio News — Daily Update")
    print("=" * 50)
    
    # 1. Read current index.html
    print("\n📄 Reading index.html...")
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # 2. Extract current articles
    print("📊 Extracting current articles...")
    current_data = extract_articles_data(html)
    if not current_data:
        print("FATAL: Could not parse articlesData")
        return
    
    existing_titles = get_existing_titles(current_data)
    print(f"   Found {len(existing_titles)} existing articles")
    
    # 3. Search with Tavily
    print("\n🔍 Searching with Tavily...")
    search_results = search_all_categories()
    
    # 4. Generate articles with Claude
    print("\n✍️ Generating articles with Claude...")
    new_articles = generate_articles_with_claude(search_results, existing_titles)
    
    if not new_articles:
        print("ERROR: Claude did not return articles. Skipping update.")
        return
    
    # 5. Merge new articles into existing data
    print("\n📝 Merging new articles...")
    total_new = 0
    for cat_id, new_arts in new_articles.items():
        if cat_id in current_data and isinstance(new_arts, list):
            # Filter out duplicates
            new_unique = [a for a in new_arts if a.get("title") not in existing_titles]
            # Prepend new articles
            current_data[cat_id] = new_unique + current_data[cat_id]
            total_new += len(new_unique)
            print(f"   {cat_id}: +{len(new_unique)} articles")
    
    print(f"\n   Total: +{total_new} new articles")
    
    if total_new == 0:
        print("No new articles to add. Skipping update.")
        return
    
    # 6. Rebuild HTML
    print("\n🔧 Updating index.html...")
    new_js = rebuild_articles_js(current_data)
    
    # Replace articlesData in HTML
    html = re.sub(
        r'let articlesData=\{.*?\};',
        new_js,
        html,
        flags=re.DOTALL
    )
    
    # Update footer date
    html = update_footer_date(html)
    
    # 7. Write updated file
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"\n✅ Done! {total_new} new articles added.")
    print("=" * 50)

if __name__ == "__main__":
    main()
