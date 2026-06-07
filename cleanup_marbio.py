import re, json
from datetime import datetime

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

def main():
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    data = extract_data(html)
    if not data:
        return

    print("Articles avant nettoyage:")
    total_before = 0
    for cat, arts in data.items():
        print(f"  {cat}: {len(arts)}")
        total_before += len(arts)
    print(f"  TOTAL: {total_before}")

    # Garder seulement les 5 plus recents par categorie
    KEEP = 5
    cleaned = {}
    for cat, arts in data.items():
        # Trier par date decroissante si possible
        def get_date(a):
            try:
                return a.get("date", "")
            except:
                return ""
        sorted_arts = sorted(arts, key=get_date, reverse=True)
        cleaned[cat] = sorted_arts[:KEEP]

    print("\nArticles apres nettoyage (5 par categorie):")
    total_after = 0
    for cat, arts in cleaned.items():
        print(f"  {cat}: {len(arts)}")
        total_after += len(arts)
    print(f"  TOTAL: {total_after}")
    print(f"\nSupprimes: {total_before - total_after} articles")

    new_js = rebuild_js(cleaned)
    html = re.sub(r'var articlesData=\{.*?\};', new_js, html, flags=re.DOTALL)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\nDone! index.html nettoye.")

if __name__ == "__main__":
    main()
