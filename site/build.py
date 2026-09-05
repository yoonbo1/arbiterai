#!/usr/bin/env python3
"""Build arbiterai.tech: wraps each page in the shared header/footer and writes /public.
Run: python3 build.py   — then deploy the public/ folder anywhere static."""
import os, shutil, datetime, email.utils
from pathlib import Path
from xml.sax.saxutils import escape

# Canonical origin for canonical/og:url/sitemap. Override on a preview deploy so the
# generated URLs point at the host actually serving the page.
SITE = os.environ.get("SITE_URL", "https://arbiterai.tech").rstrip("/")
OUT = Path("public")
NAV = [("How it works", "how-it-works.html"), ("Security model", "security.html"),
       ("Docs", "docs.html"), ("Blog", "blog.html"), ("About", "about.html")]

# Positioning, verbatim from the repositioning brief. ONE_LINER is the home page's hero sub
# and its meta/og description; SHORT is every other page's description and the footer
# tagline. The page modules import them from here so each sentence exists once.
ONE_LINER = ("Arbiter AI is an open reference implementation of HIPAA-safe document AI: "
             "de-identification before any model call, cited and verified answers, "
             "database-enforced patient isolation, and an append-only audit trail — with the "
             "evaluation harness that proves each of those properties holds.")
SHORT = "Open reference implementation of HIPAA-safe document AI, with the evals to prove it."

# The public repository (Apache-2.0) and the author's profile. Every link into the code on
# the site goes through gh()/src() so the URL is written once.
REPO = "https://github.com/yoonbo1/arbiterai"
PROFILE = "https://github.com/yoonbo1"


def repo_url(path: str = "") -> str:
    """URL of one file in the repository on the main branch, or of the repository itself."""
    return f"{REPO}/blob/main/{path}" if path else REPO


def gh(path: str, text: str | None = None) -> str:
    """A link to one file in the repository, rendered as code. `path` is relative to the
    repository root (Makefile, TODO.md, platform/worker/graph.py)."""
    return f'<a class="code-link" href="{repo_url(path)}"><code>{text or path}</code></a>'


def src(ref: str, text: str | None = None) -> str:
    """gh() for the platform, by the path the site already uses: src("worker/graph.py") links
    platform/worker/graph.py. A pytest node id (tests/test_x.py::test_y) links the file and
    keeps the full id as the text."""
    return gh("platform/" + ref.split("::", 1)[0], text or ref)


SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{site}/{path}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{site}/{path}">
<meta property="og:site_name" content="Arbiter AI">
<meta property="og:image" content="{site}/assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Arbiter AI: open reference implementation of HIPAA-safe document AI">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{site}/assets/og-image.png">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="Arbiter AI blog" href="{site}/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/styles.css">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Organization","name":"Arbiter AI","url":"{site}","logo":"{site}/assets/logo.svg","sameAs":["{repo}","{profile}"],"contactPoint":{{"@type":"ContactPoint","email":"hello@arbiterai.tech","contactType":"author"}}}}</script>
{head_extra}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-head">
  <div class="wrap">
    <a class="brand" href="/">{logo} Arbiter AI</a>
    <button class="nav-toggle" aria-expanded="false" aria-controls="nav">Menu</button>
    <nav class="nav" id="nav" aria-label="Primary">
      {navlinks}
    </nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="site-foot">
  <div class="wrap">
    <div class="foot-row">
      <a class="brand" href="/">{logo_light} Arbiter AI</a>
      <nav class="foot-links" aria-label="Footer">
        <a href="/how-it-works.html">Architecture</a>
        <a href="/security.html">Security model</a>
        <a href="/docs.html#evals">Evals</a>
        <a href="/blog.html">Blog</a>
        <a href="{repo}">GitHub</a>
        <a href="/contact.html">Contact</a>
      </nav>
    </div>
    <p class="foot-tag">{short}</p>
    <div class="foot-bottom">
      <span>&copy; <span data-year>{year}</span> Yoonbo Cho</span>
      <span>Arbiter AI is software and does not provide medical advice or make clinical decisions.</span>
    </div>
  </div>
</footer>
<script src="/assets/main.js" defer></script>
</body>
</html>
"""

LOGO = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3 L28 28 H23.2 L16 12.6 L8.8 28 H4 Z" fill="#172033"/><path d="M11 22.5 H21 L22.6 26 H9.4 Z" fill="#B08A3C"/></svg>'
LOGO_LIGHT = LOGO.replace("#172033", "#FFFFFF")


def _current(href: str, path: str) -> bool:
    """A post under /blog/ keeps the Blog nav item marked."""
    return href == path or (href == "blog.html" and path.startswith("blog/"))


def render(path: str, title: str, desc: str, body: str, meta: dict | None = None) -> str:
    """meta carries the few per-page head values the shell does not derive itself:
    og_type (default "website") and head, an extra <head> fragment in which __SITE__
    stands for the canonical origin."""
    meta = meta or {}
    links = "".join(
        f'<a href="/{href}"{" aria-current=\"page\"" if _current(href, path) else ""}>{label}</a>' for label, href in NAV)
    return SHELL.format(title=title, desc=desc, site=SITE, path=("" if path == "index.html" else path),
                        logo=LOGO, logo_light=LOGO_LIGHT, navlinks=links, body=body,
                        og_type=meta.get("og_type", "website"),
                        head_extra=meta.get("head", "").replace("__SITE__", SITE),
                        year=datetime.date.today().year, short=SHORT, repo=REPO, profile=PROFILE)


def _rfc822(iso_date: str) -> str:
    d = datetime.date.fromisoformat(iso_date)
    return email.utils.format_datetime(
        datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc))


def write_feed(posts) -> None:
    """RSS 2.0 for the blog, from the same POSTS the pages are built from."""
    items = "".join(
        "<item>"
        f"<title>{escape(p['title'])}</title>"
        f"<link>{SITE}/{p['path']}</link>"
        f"<guid isPermaLink=\"true\">{SITE}/{p['path']}</guid>"
        f"<pubDate>{_rfc822(p['date'])}</pubDate>"
        f"<description>{escape(p['summary'])}</description>"
        "</item>" for p in posts)
    newest = max((p["date"] for p in posts), default=datetime.date.today().isoformat())
    (OUT / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        "<title>Arbiter AI blog</title>"
        f"<link>{SITE}/blog.html</link>"
        f'<atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>'
        "<description>Field notes on clinical documents, health data standards, and building "
        "AI that a compliance officer can audit.</description>"
        "<language>en-us</language>"
        f"<lastBuildDate>{_rfc822(newest)}</lastBuildDate>"
        f"{items}</channel></rss>", encoding="utf-8")


def main():
    from pages import PAGES  # (path, title, description, body_html[, meta])
    from pages_blog import POSTS
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree("assets", OUT / "assets")
    for path, title, desc, body, *rest in PAGES:
        meta = rest[0] if rest else {}
        (OUT / path).parent.mkdir(parents=True, exist_ok=True)
        (OUT / path).write_text(render(path, title, desc, body, meta), encoding="utf-8")
    today = datetime.date.today().isoformat()
    urls = "".join(
        f"<url><loc>{SITE}/{'' if p == 'index.html' else p}</loc>"
        f"<lastmod>{(rest[0] if rest else {}).get('lastmod', today)}</lastmod></url>"
        for p, _t, _d, _b, *rest in PAGES if p not in ("404.html",))
    (OUT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    write_feed(POSTS)
    print(f"built {len(PAGES)} pages into {OUT}/")


if __name__ == "__main__":
    main()
