"""TechnoJobs auto page builder.
topics.json -> AI writes content -> HTML pages in site/ -> sitemap.xml
Run:  python generate.py            (needs ANTHROPIC_API_KEY or GEMINI_API_KEY)
Demo: python generate.py --demo     (no API key, placeholder text, for testing only)
"""
import json, os, re, sys, shutil, datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

SITE_URL = os.environ.get("SITE_URL", "https://www.technojobs.online")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
ROOT = Path(__file__).parent
CONTENT = ROOT / "data" / "content"
OUT = ROOT / "site"
DEMO = "--demo" in sys.argv
CLAUDE_KEY = os.environ.get("ANTHROPIC_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
HAS_KEY = bool(CLAUDE_KEY or GEMINI_KEY)
SECTIONS = {"articles": "Guides", "news": "News", "questions": "Questions"}

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

PROMPT = """Write a helpful, accurate web page for the topic: "{title}" (page type: {type}).
Audience: students and freshers in India looking for jobs and careers.
Rules: simple English, no invented facts or numbers. If unsure, say to check the official source.
Return ONLY JSON with this shape:
{{"headline": str, "description": str (max 155 chars), "intro": str,
 "highlights": [str x5], "quick_facts": [{{"label": str, "value": str}} x4],
 "sections": [{{"heading": str, "html": str (use <p>, <ul>, <li> only)}} x6],
 "faqs": [{{"q": str, "a": str}} x4]}}"""

def gemini_text(prompt):
    """Free option: Google Gemini API (key from aistudio.google.com)."""
    import time, urllib.request, urllib.error
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json"}}).encode()
    for attempt in range(5):
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            time.sleep(8)  # stay under free-tier speed limits
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 4:
                print("Busy or limit reached, waiting 30s...")
                time.sleep(30)
                continue
            raise SystemExit(f"Gemini error {e.code}: {e.read().decode()[:300]}")

def write_with_ai(title, type_):
    if DEMO:
        return {"headline": title, "description": f"{title} explained simply.",
                "intro": f"Demo introduction about {title}. Run without --demo to let AI write real text.",
                "highlights": ["Overview", "Eligibility", "Process", "Tips", "Official links"],
                "quick_facts": [{"label": "Topic", "value": title}] * 4,
                "sections": [{"heading": h, "html": "<p>Demo text.</p>"} for h in
                             ["About", "Eligibility", "Skills Required", "How to Apply", "Preparation Tips", "Useful Resources"]],
                "faqs": [{"q": f"Question {i+1} about {title}?", "a": "Demo answer."} for i in range(4)]}
    prompt = PROMPT.format(title=title, type=type_)
    if CLAUDE_KEY:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(model=MODEL, max_tokens=4000,
                                     messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text.strip()
    else:
        text = gemini_text(prompt)
    text = re.sub(r"^```(json)?|```$", "", text).strip()
    return json.loads(text)

def ld(obj):
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")

def jsonld(p):
    out = [ld({"@context": "https://schema.org", "@type": "Article", "headline": p["headline"],
               "datePublished": p["date"], "dateModified": p["date"],
               "author": {"@type": "Organization", "name": "TechnoJobs Team"}})]
    if p.get("faqs"):
        out.append(ld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
            for f in p["faqs"]]}))
    return out

def main():
    topics = json.loads((ROOT / "topics.json").read_text())
    CONTENT.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    # 1. write content for new topics only
    for t in topics:
        slug = slugify(t["title"])
        f = CONTENT / f"{t['type']}__{slug}.json"
        if f.exists():
            continue
        if not DEMO and not HAS_KEY:
            print("Skipped (no API key here, GitHub will write it):", t["title"])
            continue
        print("Writing:", t["title"])
        data = write_with_ai(t["title"], t["type"])
        data.update(title=t["title"], type=t["type"], slug=slug, date=today)
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    # 2. build all pages
    pages = sorted((json.loads(p.read_text()) for p in CONTENT.glob("*.json")),
                   key=lambda p: p["date"], reverse=True)
    jobs_file = ROOT / "data" / "jobs.json"
    jobs = json.loads(jobs_file.read_text()) if jobs_file.exists() else []
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    shutil.copy(ROOT / "assets" / "style.css", OUT / "assets" / "style.css")
    ctx = dict(site_url=SITE_URL, nav=list(SECTIONS.items()), jobs=jobs[:4])
    for p in pages:
        related = [r for r in pages if r["slug"] != p["slug"]][:3]
        html = env.get_template("page.html").render(p=p, related=related, section=SECTIONS[p["type"]], ld=jsonld(p), **ctx)
        d = OUT / p["type"] / p["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html)
    for typ, label in SECTIONS.items():
        items = [p for p in pages if p["type"] == typ]
        d = OUT / typ
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(env.get_template("list.html").render(title=label, items=items, **ctx))
    (OUT / "index.html").write_text(env.get_template("list.html").render(title="Latest articles", items=pages[:30], home=True, **ctx))
    urls = [f"{SITE_URL}/"] + [f"{SITE_URL}/{p['type']}/{p['slug']}/" for p in pages]
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls) + "\n</urlset>\n")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    print(f"Built {len(pages)} pages in site/")

if __name__ == "__main__":
    main()