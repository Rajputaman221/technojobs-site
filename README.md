# TechnoJobs auto page system

topic -> Claude writes -> HTML pages -> GitHub -> Cloudflare Pages -> Google

## One-time setup (about 20 minutes)
1. Create a GitHub repository and upload all these files.
2. GitHub > Settings > Secrets and variables > Actions > New secret:
   name `ANTHROPIC_API_KEY`, value = your key from console.anthropic.com
3. Cloudflare > Workers & Pages > Create > Pages > Connect to Git > choose the repo.
   - Build command: `pip install -r requirements.txt && python generate.py`
   - Build output directory: `site`
   - No API key needed here. GitHub writes the content and saves it in `data/content`;
     Cloudflare only turns the saved content into the website.
4. Add your domain technojobs.online in Cloudflare Pages > Custom domains.
5. Google Search Console > add the site > submit `https://www.technojobs.online/sitemap.xml`

## Add a topic (3 ways)
- Edit `topics.json` on GitHub (works on phone). The workflow starts by itself.
- GitHub > Actions > Generate pages > Run workflow > type the topic.
- Later: a Telegram bot that calls the same workflow.

## Test on your computer
    pip install -r requirements.txt
    python generate.py --demo        # demo text, for testing only (then delete data/content/*.json)
    python generate.py               # real Claude text (set ANTHROPIC_API_KEY)
Open `site/index.html` in a browser.

## Safety
Read each new page before you trust it. AI can make mistakes. Do not publish thousands of
pages at once. 10 to 20 good pages a day is enough.
