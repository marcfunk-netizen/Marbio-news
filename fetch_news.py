import json, os, urllib.request
from datetime import datetime, timedelta, timezone

API_KEY = os.environ["TAVILY_API_KEY"]
URL = "https://api.tavily.com/search"

QUERIES = {
    "african-cdc":            "Africa CDC 2026",
    "african-medical-agency": "African Medicines Agency AMA 2026",
    "manufacture-vaccins":    "vaccine manufacturing Africa 2026",
    "unicef-gavi":            "UNICEF GAVI vaccine Africa 2026",
    "sante-maroc":            "sante Maroc vaccins 2026",
    "vaccins-monde":          "WHO vaccine news 2026",
}

CATEGORIES = [
    {"id": "african-cdc",            "label": "Africa CDC",                     "icon": "🌍", "desc": "Publications et communiques"},
    {"id": "african-medical-agency", "label": "Agence Africaine du Medicament",  "icon": "💊", "desc": "Actualites reglementaires (AMA)"},
    {"id": "manufacture-vaccins",    "label": "Manufacture Vaccins Afrique",     "icon": "🏭", "desc": "Production vaccins et biologiques"},
    {"id": "unicef-gavi",            "label": "UNICEF & GAVI",                   "icon": "💉", "desc": "Campagnes d immunisation"},
    {"id": "sante-maroc",            "label": "Sante Maroc",                     "icon": "🇲🇦", "desc": "Systeme de soins marocain"},
    {"id": "vaccins-monde",          "label": "Vaccins dans le Monde",           "icon": "🌐", "desc": "Actualites mondiales vaccination"},
]

CUTOFF = datetime.now(timezone.utc) - timedelta(days=60)

def parse_date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
        except:
            pass
    return None

articles_data = {}
for cat_id, query in QUERIES.items():
    payload = json.dumps({
        "api_key": API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": 10,
        "include_answer": False,
        "include_raw_content": False,
        "days": 60,
    }).encode()
    req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        articles = []
        for item in data.get("results", []):
            pub = parse_date(item.get("published_date", ""))
            if pub and pub < CUTOFF:
                continue
            articles.append({
                "title":   item.get("title", "").replace('"', '\\"').replace('\n', ' '),
                "url":     item.get("url", ""),
                "content": item.get("content", "").replace('"', '\\"').replace('\n', ' '),
                "date":    item.get("published_date", "") or "",
            })
        articles_data[cat_id] = articles
        print(f"OK {cat_id}: {len(articles)} articles")
    except Exception as e:
        print(f"ERR {cat_id}: {e}")
        articles_data[cat_id] = []

# Also save data.json
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(articles_data, f, ensure_ascii=False, indent=2)

today = datetime.now().strftime("%-d %B %Y").lower()
# French month names
months = {"january":"janvier","february":"février","march":"mars","april":"avril",
          "may":"mai","june":"juin","july":"juillet","august":"août",
          "september":"septembre","october":"octobre","november":"novembre","december":"décembre"}
for en, fr in months.items():
    today = today.replace(en, fr)

articles_js = json.dumps(articles_data, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Marbio News</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧬</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'DM Sans',system-ui,sans-serif;background:linear-gradient(168deg,#F0F6FC 0%,#E8F0FE 35%,#F7F9FC 100%);min-height:100vh;color:#0A1929}}
.header{{background:linear-gradient(135deg,#001F3D 0%,#003366 40%,#00538A 100%);padding:26px 20px 20px;position:relative;overflow:hidden}}
.header::before{{content:'';position:absolute;top:-50px;right:-30px;width:180px;height:180px;border-radius:50%;background:rgba(255,255,255,0.03)}}
.header-inner{{max-width:820px;margin:0 auto;position:relative}}
.logo-row{{display:flex;align-items:center;gap:14px;margin-bottom:4px}}
.logo-icon{{width:46px;height:46px;border-radius:13px;background:linear-gradient(135deg,rgba(255,255,255,0.14),rgba(255,255,255,0.06));display:flex;align-items:center;justify-content:center;font-size:24px;border:1px solid rgba(255,255,255,0.12)}}
.logo-title{{font-family:'Source Serif 4',Georgia,serif;font-size:28px;font-weight:700;color:#fff;letter-spacing:-0.5px}}
.logo-sub{{font-size:11.5px;color:rgba(255,255,255,0.5);letter-spacing:1.8px;text-transform:uppercase;font-weight:500;margin-top:2px}}
.search-row{{display:flex;gap:8px;margin-top:18px}}
.search-wrap{{flex:1;position:relative}}
.search-input{{width:100%;padding:12px 16px 12px 42px;border-radius:12px;border:1px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.08);color:#fff;font-size:13.5px;outline:none;font-family:inherit;transition:all .2s}}
.search-input:focus{{background:rgba(255,255,255,0.14);border-color:rgba(255,255,255,0.25)}}
.search-input::placeholder{{color:#9AB0C6}}
.search-btn{{padding:12px 22px;border-radius:12px;border:none;background:#fff;color:#00538A;font-weight:650;font-size:13px;cursor:pointer;white-space:nowrap;font-family:inherit}}
.main{{max-width:820px;margin:0 auto;padding:18px 16px 40px}}
.categories{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:22px}}
.cat-btn{{padding:14px;border-radius:14px;border:1px solid rgba(0,40,80,0.07);background:#fff;color:#2A3B4E;cursor:pointer;text-align:left;transition:all .25s;box-shadow:0 1px 4px rgba(0,40,80,0.04);font-family:inherit}}
.cat-btn:hover{{box-shadow:0 4px 12px rgba(0,105,180,0.1);transform:translateY(-1px)}}
.cat-btn.active{{border:2px solid #0069B4;background:linear-gradient(135deg,#0069B4,#00538A);color:#fff;box-shadow:0 6px 20px rgba(0,105,180,0.2)}}
.cat-icon{{font-size:20px;margin-bottom:5px}}
.cat-label{{font-size:12.5px;font-weight:650;line-height:1.3;margin-bottom:3px}}
.cat-desc{{font-size:10.5px;line-height:1.4;opacity:.5}}
.cat-btn.active .cat-desc{{opacity:.8}}
.toolbar{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px}}
.toolbar-info{{font-size:12px;color:#7A8A9E}}
.toolbar-right{{display:flex;align-items:center;gap:10px}}
.hint{{font-size:11px;color:#9AB0C6;background:rgba(0,105,180,0.05);padding:4px 10px;border-radius:6px}}
.articles{{display:flex;flex-direction:column;gap:12px}}
.article-card{{background:#fff;border-radius:16px;border:1px solid rgba(0,40,80,0.07);padding:20px 22px;transition:all .25s;animation:fadeSlideIn .4s ease both}}
.article-card:hover{{border-color:rgba(0,105,180,0.2);transform:translateY(-1px);box-shadow:0 8px 30px rgba(0,105,180,0.08)}}
.article-card.is-new{{border-left:4px solid #E8A020;background:linear-gradient(135deg,#FFFDF5,#fff 30%)}}
.article-inner{{display:flex;gap:14px;align-items:flex-start}}
.article-bar{{width:6px;min-height:50px;border-radius:3px;opacity:.7;flex-shrink:0;margin-top:2px}}
.article-body{{flex:1;min-width:0}}
.article-title{{font-family:'Source Serif 4',Georgia,serif;font-size:15.5px;font-weight:650;line-height:1.45;color:#0A1929;text-decoration:none;display:block;margin-bottom:10px}}
.article-title:hover{{color:#0069B4}}
.article-content{{font-size:13.5px;line-height:1.7;color:#3A4D62;margin-bottom:14px;overflow:hidden}}
.article-content.collapsed{{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}}
.article-meta{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.source-tag{{padding:3px 10px;border-radius:6px;font-weight:600;font-size:11px}}
.date-tag{{font-size:11.5px;color:#8A9BB0}}
.badge-new{{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:1px;text-transform:uppercase;padding:3px 9px;border-radius:6px;background:linear-gradient(135deg,#E8A020,#F0C040);color:#fff;animation:pulse 2s ease-in-out infinite;box-shadow:0 2px 8px rgba(232,160,32,0.3)}}
.expand-btn{{background:none;border:1px solid rgba(0,105,180,0.15);border-radius:6px;padding:3px 10px;color:#0069B4;font-size:11px;font-weight:600;cursor:pointer;margin-left:auto;font-family:inherit}}
.expand-btn:hover{{background:rgba(0,105,180,0.05)}}
.spinner-wrap{{display:flex;flex-direction:column;align-items:center;padding:50px 0}}
.spinner-text{{color:#5A7A96;font-size:14px;font-weight:500}}
.new-count{{font-size:11px;color:#E8A020;background:rgba(232,160,32,0.08);border:1px solid rgba(232,160,32,0.2);padding:4px 10px;border-radius:6px;font-weight:600;margin-left:8px}}
.footer{{margin-top:50px;padding-top:22px;border-top:1px solid rgba(0,40,80,0.06);text-align:center;font-size:11px;color:#9AB0C6;line-height:2}}
.footer strong{{color:#4A6A84;font-weight:600;font-size:12px}}
@keyframes fadeSlideIn{{from{{opacity:0;transform:translateY(14px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
@media(max-width:640px){{.categories{{grid-template-columns:repeat(2,1fr)}}.toolbar{{flex-direction:column;align-items:flex-start}}.toolbar-right{{width:100%;justify-content:space-between}}}}
</style>
</head>
<body>
<header class="header">
<div class="header-inner">
<div class="logo-row">
<div class="logo-icon">🧬</div>
<div>
<div class="logo-title">Marbio News</div>
<div class="logo-sub">Veille Vaccins · Sante · Afrique · Maroc · Monde</div>
</div>
</div>
<div class="search-row">
<div class="search-wrap">
<span class="search-icon">🔍</span>
<input type="text" class="search-input" id="searchInput" placeholder="Recherche libre...">
</div>
<button class="search-btn" id="searchBtn">Rechercher</button>
</div>
</div>
</header>
<main class="main">
<div class="categories" id="categories"></div>
<div class="toolbar">
<div>
<span class="toolbar-info" id="toolbarInfo"></span>
<span class="new-count" id="newCount" style="display:none"></span>
</div>
<div class="toolbar-right">
<div class="hint">Lire plus pour le resume complet</div>
</div>
</div>
<div class="articles" id="articles"></div>
<footer class="footer">
<strong>Marbio News</strong><br>
Veille sanitaire automatique · Africa CDC · AMA · UNICEF · GAVI · Maroc · Monde<br>
Mis à jour le {today}
</footer>
</main>
<script>
var CATEGORIES={json.dumps(CATEGORIES, ensure_ascii=False)};
var activeCategory="african-cdc";
var isCustomSearch=false;
var articlesData={articles_js};
function getSourceColor(d){{if(d.includes("who.int"))return"#0093D5";if(d.includes("africacdc")||d.includes("au.int"))return"#1B8C3A";if(d.includes("unicef"))return"#00AEEF";if(d.includes("gavi"))return"#E8702A";if(d.includes(".ma")||d.includes("maroc")||d.includes("santemag")||d.includes("hespress"))return"#C1272D";if(d.includes("nature.com"))return"#B5232D";if(d.includes("path.org"))return"#6B2D8B";if(d.includes("cdc.gov"))return"#075290";return"#0069B4";}}
function extractDomain(u){{try{{return new URL(u).hostname.replace("www.","")}}catch(e){{return""}}}}
function timeAgo(d){{if(!d)return"";var date=new Date(d),now=new Date();if(isNaN(date))return"";var s=Math.floor((now-date)/1000);var formatted=date.toLocaleDateString("fr-FR",{{day:"numeric",month:"long",year:"numeric"}});if(s>=0&&s<86400)return formatted+" - aujourd hui";if(s>=86400&&s<172800)return formatted+" - hier";if(s>=172800&&s<604800)return formatted+" - il y a "+Math.floor(s/86400)+"j";return formatted;}}
function isRecent(d){{if(!d)return false;var date=new Date(d),now=new Date(),diff=(now-date)/(1000*60*60*24);return diff<=1.5;}}
function renderCategories(){{var el=document.getElementById("categories");el.innerHTML=CATEGORIES.map(function(c){{var articles=articlesData[c.id]||[];var newCount=articles.filter(function(a){{return isRecent(a.date)}}).length;var badge=newCount>0?'<span style="font-size:9px;background:#E8A020;color:#fff;padding:1px 5px;border-radius:4px;margin-left:4px;font-weight:800">'+newCount+' NEW</span>':"";return'<button class="cat-btn '+(activeCategory===c.id&&!isCustomSearch?"active":"")+'" data-id="'+c.id+'"><div class="cat-icon">'+c.icon+'</div><div class="cat-label">'+c.label+badge+'</div><div class="cat-desc">'+c.desc+'</div></button>';}}).join("");el.querySelectorAll(".cat-btn").forEach(function(b){{b.addEventListener("click",function(){{isCustomSearch=false;activeCategory=b.dataset.id;renderCategories();renderArticles();}});}});}}
function renderArticles(){{var container=document.getElementById("articles");var articles=articlesData[activeCategory]||[];var info=document.getElementById("toolbarInfo");var newArticles=articles.filter(function(a){{return isRecent(a.date)}});var newCountEl=document.getElementById("newCount");info.textContent=articles.length+" articles";if(newArticles.length>0){{newCountEl.style.display="inline";newCountEl.textContent="NEW "+newArticles.length+" nouveau"+(newArticles.length>1?"x":"");}}else{{newCountEl.style.display="none";}}if(!articles.length){{container.innerHTML='<div class="spinner-wrap" style="padding:40px 0"><div style="font-size:52px;opacity:.3;margin-bottom:14px">📰</div><div class="spinner-text">Aucun article</div></div>';return;}}container.innerHTML=articles.map(function(a,i){{var domain=extractDomain(a.url),color=getSourceColor(domain),dateStr=timeAgo(a.date);var isNew=isRecent(a.date);return'<div class="article-card'+(isNew?" is-new":"")+'" style="animation-delay:'+i*.06+'s"><div class="article-inner"><div class="article-bar" style="background:'+color+'"></div><div class="article-body"><a href="'+a.url+'" target="_blank" rel="noopener" class="article-title">'+(isNew?'<span class="badge-new">NOUVEAU</span> ':'')+a.title+'</a><div class="article-content collapsed" id="c-'+i+'">'+a.content+'</div><div class="article-meta"><span class="source-tag" style="background:'+color+'14;color:'+color+'">'+domain+'</span>'+(dateStr?'<span class="date-tag">'+dateStr+'</span>':'')+'<button class="expand-btn" data-i="'+i+'">Lire plus</button></div></div></div></div>';}}).join("");container.querySelectorAll(".expand-btn").forEach(function(b){{b.addEventListener("click",function(){{var el=document.getElementById("c-"+b.dataset.i);var c=el.classList.toggle("collapsed");b.textContent=c?"Lire plus":"Reduire";}});}});}}
function doSearch(){{var val=document.getElementById("searchInput").value.trim().toLowerCase();if(!val){{isCustomSearch=false;renderCategories();renderArticles();return;}}isCustomSearch=true;var allArticles=[];Object.values(articlesData).forEach(function(arr){{if(Array.isArray(arr))arr.forEach(function(a){{allArticles.push(a)}})}}); var filtered=allArticles.filter(function(a){{return(a.title+a.content).toLowerCase().includes(val)}});activeCategory="search-custom";articlesData["search-custom"]=filtered;renderCategories();renderArticles();}}
document.getElementById("searchBtn").addEventListener("click",doSearch);
document.getElementById("searchInput").addEventListener("keydown",function(e){{if(e.key==="Enter")doSearch()}});
renderCategories();
renderArticles();
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("index.html written.")
