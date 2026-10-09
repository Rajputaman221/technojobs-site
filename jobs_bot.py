"""JobFinder auto jobs bot.

Every run it:
  1. finds jobs in India with direct company links (JobsPipe),
  2. posts new ones to your Telegram channel (optional),
  3. adds new ones to js/data.js so your website shows them (at most every few hours).

Runs on GitHub Actions (.github/workflows/post-jobs.yml). No extra packages needed.
Test without posting or writing:  python jobs_bot.py --dry
"""
import hashlib, json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
import company_feeds

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "jobs_bot_config.json"), encoding="utf-8"))
_lvl = os.environ.get("JOB_LEVEL", "").strip()
if _lvl in ("All", "Fresher", "Experienced"):
    CFG["level"] = _lvl        # Telegram
    CFG["site_level"] = _lvl   # website
STATE_PATH = os.path.join(HERE, "bot_state.json")
DATA_JS = os.path.join(HERE, CFG.get("data_js_path", "js/data.js"))

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT", "").strip()
KEY = os.environ.get("JOBSPIPE_KEY", "").strip()
FORCE_SITE = os.environ.get("FORCE_SITE", "").strip().lower() in ("1", "true", "yes")
DRY = "--dry" in sys.argv

DIRECT_SOURCES = ["greenhouse", "lever", "ashby", "workday", "smartrecruiters", "workable", "recruitee", "personio"]
SENIOR_RE = re.compile(r"senior|\bsr\b|lead\b|principal|staff|manager|architect|director|head of|vp\b", re.I)
FRESHER_RE = re.compile(r"fresher|entry.level|intern\b|internship|trainee|graduate engineer|graduate|junior|jr\.?\b|0\s*-\s*1 years?|0\s*-\s*2 years?", re.I)
NO_DESC = "Open the apply link to read the full job description on the company's official careers page."


def now():
    return datetime.now(timezone.utc)


def load_state():
    try:
        s = json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception:
        s = {}
    s.setdefault("sent", [])
    s.setdefault("site_keys", [])
    s.setdefault("pending", [])
    s.setdefault("last_site_update", "")
    return s


def post_json(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def search_jobspipe(skill, city):
    body = {"job_country_code_or": ["IN"], "posted_at_max_age_days": 3, "limit": int(CFG.get("limit_per_skill", 25))}
    direct = CFG.get("direct_company_links_only", True)
    if direct:
        body["source_or"] = DIRECT_SOURCES
    if skill:
        body["job_title_or"] = [skill]
    if city:
        body["job_location_or"] = [city]
    data = None
    for attempt in range(3):
        try:
            data = post_json("https://api.jobspipe.dev/v1/jobs/search", body,
                             {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
            break
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(8 * (attempt + 1))  # rate limited: wait and retry
    if data is None:
        raise RuntimeError("rate limited (HTTP 429)")
    time.sleep(2.5)  # be gentle with the API between searches

    out = []
    for j in data.get("data", []):
        url = j.get("source_url") or ((j.get("sources") or [{}])[0].get("url")) or ""
        if not url:
            continue
        if direct and re.search(r"linkedin\.com|indeed\.", url, re.I):
            continue
        title = (j.get("job_title") or "").strip()
        seniority = j.get("seniority") or ""
        text = title + " " + seniority
        if SENIOR_RE.search(text):
            level = "Experienced"
        elif FRESHER_RE.search(text):
            level = "Fresher"
        else:
            level = "Experienced"
        sal = ""
        if j.get("min_annual_salary_usd"):
            sal = "USD %s" % j["min_annual_salary_usd"] + (" - %s" % j["max_annual_salary_usd"] if j.get("max_annual_salary_usd") else "")
        key = hashlib.sha1(url.encode()).hexdigest()[:12]
        tags = j.get("technology_slugs") or []
        out.append({
            "id": "auto-" + key,
            "title": title,
            "company": j.get("company") or "",
            "logo": "",
            "location": (j.get("location") or "India") + (" (Remote)" if j.get("remote") else ""),
            "type": "Internship" if re.search(r"intern", text, re.I) else "Full-time",
            "qualification": "Not specified",
            "level": level,
            "years": "0 years" if level == "Fresher" else "Not specified",
            "role": title,
            "pay": sal or "Not disclosed",
            "requirements": "\n".join(tags[:15]),
            "details": NO_DESC,
            "link": url,
            "posted": (j.get("date_posted") or "")[:10] or now().strftime("%Y-%m-%d"),
        })
    return out


def dupe_key(j):
    clean = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    return clean(j.get("company")) + "|" + clean(j.get("title"))


def search(skill, city):
    limit = int(CFG.get("limit_per_skill", 25))
    out, seen = [], set()

    def add(jobs):
        for j in jobs:
            k = dupe_key(j)
            if k in seen or len(out) >= limit:
                continue
            seen.add(k)
            out.append(j)

    # (company career feeds are read once per run in main(), see company_feeds.bulk)

    # JobsPipe (direct company links)
    if CFG.get("use_jobspipe", True) and KEY and len(out) < limit:
        try:
            add(search_jobspipe(skill, city))
        except Exception as e:
            print("JobsPipe failed:", e)

    # Adzuna (links go through Adzuna's own page, so it is OFF unless use_adzuna is true)
    if CFG.get("use_adzuna", False) and len(out) < limit:
        try:
            import adzuna_source
            if adzuna_source.enabled():
                add(adzuna_source.search(skill, city, CFG, SENIOR_RE, FRESHER_RE, NO_DESC))
        except Exception as e:
            print("Adzuna failed:", e)

    return out

def telegram(text):
    body = {"chat_id": CHAT, "text": text, "disable_web_page_preview": True}
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    for _ in range(3):
        try:
            post_json(url, body, {"Content-Type": "application/json"})
            return True
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")
            if e.code == 429:
                try:
                    wait = json.loads(detail)["parameters"]["retry_after"]
                except Exception:
                    wait = 10
                time.sleep(wait + 1)
                continue
            print("Telegram error", e.code, detail[:200])
            return False
    return False


def on_site(j):
    """True when this job is going to be added to the website (so its job page will exist)."""
    if not CFG.get("update_website", True):
        return False
    return CFG.get("site_level", "All") in ("All", j["level"])


def job_line(j):
    base = (CFG.get("website_url") or "").rstrip("/")
    if base and on_site(j):
        # opens ONLY this job on our website; its Apply button goes to the company page
        return "View & apply: " + base + "/job/" + j["id"] + "/"
    return "Apply (company website): " + j["link"]


def message_base(j):
    lines = [
        "NEW JOB: " + j["title"],
        "Company: " + j["company"],
        "Location: " + j["location"],
        "Level: " + j["level"] + " | " + j["type"],
        "Pay: " + j["pay"],
        "",
        job_line(j),
    ]
    if CFG.get("website_url"):
        lines += ["", "More jobs: " + CFG["website_url"]]
    return "\n".join(lines)


def via(link):
    from urllib.parse import urlparse
    host = urlparse(link or "").netloc.lower()
    portals = {"adzuna": "Adzuna", "naukri": "Naukri", "indeed": "Indeed", "linkedin": "LinkedIn", "glassdoor": "Glassdoor", "foundit": "Foundit", "monster": "Monster", "shine": "Shine", "timesjobs": "TimesJobs", "internshala": "Internshala", "instahyre": "Instahyre", "wellfound": "Wellfound", "freshersworld": "Freshersworld", "apna": "Apna"}
    for k, v in portals.items():
        if k in host:
            return v + " (job portal)"
    return "Company website"


def message(j):
    return message_base(j) + "\nApply via: " + via(j.get("link"))

def is_adzuna(link):
    from urllib.parse import urlparse
    return "adzuna" in urlparse(link or "").netloc.lower()


def remove_adzuna():
    """Deletes every job whose apply link goes through Adzuna from js/data.js. Returns how many were removed."""
    text = open(DATA_JS, encoding="utf-8").read()
    idx = text.index("window.SITE_DEFAULT")
    start = text.index("{", idx)
    end = text.rindex("}")
    obj = json.loads(text[start:end + 1])
    jobs = obj.get("jobs", [])
    kept = [j for j in jobs if not is_adzuna(j.get("link"))]
    if len(kept) == len(jobs):
        return 0
    obj["jobs"] = kept
    out = "/* Default website data. The jobs list is updated automatically by jobs_bot.py */\nwindow.SITE_DEFAULT = " \
          + json.dumps(obj, indent=2, ensure_ascii=False) + ";\n"
    open(DATA_JS, "w", encoding="utf-8").write(out)
    return len(jobs) - len(kept)


def write_job_pages(jobs):
    """Creates job/<id>/index.html for every job on the website (own page + link preview with the job title)
    and deletes the pages of jobs that are no longer listed."""
    import html, shutil
    root = os.path.join(os.path.dirname(os.path.abspath(DATA_JS)), "..", "job")
    root = os.path.normpath(root)
    tpl_path = os.path.join(root, "index.html")
    if not os.path.exists(tpl_path):
        print("job/index.html template missing: job pages not created")
        return
    tpl = open(tpl_path, encoding="utf-8").read()
    tpl = tpl.replace('href="../', 'href="../../').replace('src="../', 'src="../../')
    safe = lambda i: bool(re.fullmatch(r"[A-Za-z0-9_-]+", str(i or "")))
    wanted = set()
    for j in jobs:
        if not safe(j.get("id")):
            continue
        wanted.add(j["id"])
        title = "%s at %s - TechnoJobs" % (j.get("title", ""), j.get("company", ""))
        desc = "%s | %s | %s. View the job and apply on the company's official page." % (
            j.get("location", ""), j.get("type", ""), j.get("level", ""))
        page = re.sub(r"<title>.*?</title>", "<title>%s</title>" % html.escape(title), tpl, count=1, flags=re.S)
        page = re.sub(r'<meta property="og:title"[^>]*>', '<meta property="og:title" content="%s">' % html.escape(title, quote=True), page, count=1)
        page = re.sub(r'<meta property="og:description"[^>]*>', '<meta property="og:description" content="%s">' % html.escape(desc, quote=True), page, count=1)
        site = (CFG.get("website_url") or "").rstrip("/")
        extra = '<meta property="og:type" content="website">\n<meta name="twitter:card" content="summary">\n'
        extra += '<meta name="description" content="%s">\n' % html.escape(desc, quote=True)
        if site:
            jurl = "%s/job/%s/" % (site, j["id"])
            extra += '<meta property="og:url" content="%s">\n<link rel="canonical" href="%s">\n' % (jurl, jurl)
        page = page.replace('<link rel="preconnect" href="https://fonts.googleapis.com">', extra + '<link rel="preconnect" href="https://fonts.googleapis.com">', 1)
        page = page.replace('<script src="../../js/job.js">', '<script>window.JOB_ID=%s;</script>\n<script src="../../js/job.js">' % json.dumps(j["id"]), 1)
        d = os.path.join(root, j["id"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(page)
    for name in os.listdir(root):
        full = os.path.join(root, name)
        if os.path.isdir(full) and name not in wanted:
            shutil.rmtree(full, ignore_errors=True)
    print("job pages: %d" % len(wanted))


def update_data_js(new_jobs):
    """Adds new_jobs to the jobs list in js/data.js. Everything else in the file stays as it is."""
    text = open(DATA_JS, encoding="utf-8").read()
    idx = text.index("window.SITE_DEFAULT")
    start = text.index("{", idx)
    end = text.rindex("}")
    obj = json.loads(text[start:end + 1])  # raises if the file is not plain JSON: nothing is written
    jobs = obj.get("jobs", [])
    have = set(j.get("link") for j in jobs)
    add = [j for j in new_jobs if j["link"] not in have and not is_adzuna(j["link"])]
    add.sort(key=lambda j: j["posted"], reverse=True)
    jobs = add + jobs

    # tidy up: only jobs added by this bot (id starts with "auto-") are ever removed
    keep_days = int(CFG.get("keep_days", 45))
    cutoff = now().timestamp() - keep_days * 86400
    def stale(j):
        if not str(j.get("id", "")).startswith("auto-"):
            return False
        try:
            return datetime.strptime(j.get("posted", "")[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() < cutoff
        except Exception:
            return False
    jobs = [j for j in jobs if not stale(j)]
    cap = int(CFG.get("max_auto_jobs_on_site", 300))
    seen_auto, kept = 0, []
    for j in jobs:
        if str(j.get("id", "")).startswith("auto-"):
            seen_auto += 1
            if seen_auto > cap:
                continue
        kept.append(j)
    obj["jobs"] = kept
    out = "/* Default website data. The jobs list is updated automatically by jobs_bot.py */\nwindow.SITE_DEFAULT = " \
          + json.dumps(obj, indent=2, ensure_ascii=False) + ";\n"
    open(DATA_JS, "w", encoding="utf-8").write(out)
    try:
        write_job_pages(kept)
    except Exception as e:
        print("could not create job pages:", e)
    return len(add)


def main():
    use_tg = bool(TOKEN and CHAT)
    if not DRY and CFG.get("remove_adzuna_jobs", True):
        try:
            print("removed %d Adzuna jobs from the website" % remove_adzuna())
        except Exception as e:
            print("could not clean Adzuna jobs:", e)
    state = load_state()
    sent, site_keys = set(state["sent"]), set(state["site_keys"])

    cities = CFG.get("cities") or [""]
    found = {}
    try:
        for j in company_feeds.bulk(CFG, SENIOR_RE, FRESHER_RE, NO_DESC):
            found.setdefault(j["id"], j)
    except Exception as e:
        print("company feeds failed:", e)
    for skill in (CFG.get("skills", [""]) if (KEY and CFG.get("use_jobspipe", True)) else []):
        for city in cities:
            try:
                for j in search(skill, city):
                    found.setdefault(j["id"], j)
            except Exception as e:
                print("search failed for %r/%r: %s" % (skill, city, e))
    print("found %d jobs" % len(found))

    # ---- website queue ----
    site_level = CFG.get("site_level", "All")
    pending_ids = set(j["id"] for j in state["pending"])
    update_site = bool(CFG.get("update_website", True))
    for j in (found.values() if update_site else []):
        if j["id"] in site_keys or j["id"] in pending_ids:
            continue
        if site_level != "All" and j["level"] != site_level:
            continue
        state["pending"].append(j)
        site_keys.add(j["id"])
    state["pending"] = state["pending"][-5000:]

    # ---- Telegram ----
    posted = 0
    if use_tg:
        want = CFG.get("level", "All")
        jobs = [j for j in found.values() if j["id"] not in sent and (want == "All" or j["level"] == want)]
        jobs.sort(key=lambda j: j["posted"], reverse=True)
        print("new for Telegram: %d" % len(jobs))
        for j in jobs[: int(CFG.get("max_posts_per_run", 40))]:
            if DRY:
                print(message(j), "\n---")
                continue
            if telegram(message(j)):
                sent.add(j["id"])
                posted += 1
                time.sleep(3.2)  # stay under Telegram's ~20 messages/minute limit
            else:
                break
    else:
        print("Telegram secrets not set: skipping Telegram")

    # ---- website (data.js), at most every site_update_hours ----
    last = state["last_site_update"]
    due = True
    if last and not FORCE_SITE:
        try:
            due = (now() - datetime.fromisoformat(last)).total_seconds() >= float(CFG.get("site_update_hours", 6)) * 3600
        except Exception:
            due = True
    added = 0
    if update_site and state["pending"] and due and not DRY:
        try:
            added = update_data_js(state["pending"])
            state["pending"] = []
            state["last_site_update"] = now().isoformat()
        except Exception as e:
            print("could not update data.js (left unchanged):", e)
    if update_site:
        print("website: %d jobs added, %d waiting for the next update" % (added, len(state["pending"])))
    else:
        print("website updates are OFF (Telegram only)")

    if not DRY:
        state["sent"] = list(sent)[-5000:]
        state["site_keys"] = list(site_keys)[-8000:]
        json.dump(state, open(STATE_PATH, "w", encoding="utf-8"))
    print("posted to Telegram: %d" % posted)


if __name__ == "__main__":
    main()


