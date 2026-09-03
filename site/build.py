#!/usr/bin/env python3
"""Build arbiterai.tech: wraps each page in the shared header/footer and writes /public.
Run: python3 build.py   — then deploy the public/ folder anywhere static."""
import os, shutil, datetime
from pathlib import Path

SITE = "https://arbiterai.tech"
OUT = Path("public")
NAV = [("Product", "product.html"), ("Security", "security.html"), ("Pricing", "pricing.html"),
       ("Docs", "docs.html"), ("About", "about.html")]

SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{site}/{path}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{site}/{path}">
<meta property="og:image" content="{site}/assets/og-image.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/styles.css">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Organization","name":"Arbiter AI","url":"{site}","logo":"{site}/assets/logo.svg","contactPoint":{{"@type":"ContactPoint","email":"hello@arbiterai.tech","contactType":"sales"}}}}</script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-head">
  <div class="wrap">
    <a class="brand" href="/">{logo} Arbiter AI</a>
    <button class="nav-toggle" aria-expanded="false" aria-controls="nav">Menu</button>
    <nav class="nav" id="nav" aria-label="Primary">
      {navlinks}
      <a class="btn btn-primary" href="/contact.html">Request a demo</a>
    </nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="site-foot">
  <div class="wrap">
    <div class="foot-grid">
      <div>
        <a class="brand" href="/">{logo_light} Arbiter AI</a>
        <p>Private, auditable AI for clinical documents. Runs in your environment or ours, under a signed BAA.</p>
      </div>
      <div><h4>Product</h4><a href="/product.html">How it works</a><a href="/security.html">Security &amp; compliance</a><a href="/pricing.html">Pricing</a><a href="/docs.html">Documentation</a></div>
      <div><h4>Company</h4><a href="/about.html">About</a><a href="/contact.html">Contact</a><a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a></div>
      <div><h4>Legal</h4><a href="/privacy.html">Privacy policy</a><a href="/terms.html">Terms of service</a><a href="/security.html#baa">Business associate agreement</a></div>
    </div>
    <div class="foot-bottom">
      <span>&copy; <span data-year></span> Arbiter AI. All rights reserved.</span>
      <span>Arbiter AI is a software vendor and does not provide medical advice or make clinical decisions.</span>
    </div>
  </div>
</footer>
<script src="/assets/main.js" defer></script>
</body>
</html>
"""

LOGO = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3 L28 28 H23.2 L16 12.6 L8.8 28 H4 Z" fill="#172033"/><path d="M11 22.5 H21 L22.6 26 H9.4 Z" fill="#B08A3C"/></svg>'
LOGO_LIGHT = LOGO.replace("#172033", "#FFFFFF")


def render(path: str, title: str, desc: str, body: str) -> str:
    links = "".join(
        f'<a href="/{href}"{" aria-current=\"page\"" if href == path else ""}>{label}</a>' for label, href in NAV)
    return SHELL.format(title=title, desc=desc, site=SITE, path=("" if path == "index.html" else path),
                        logo=LOGO, logo_light=LOGO_LIGHT, navlinks=links, body=body)


def main():
    from pages import PAGES  # list of (path, title, description, body_html)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree("assets", OUT / "assets")
    for path, title, desc, body in PAGES:
        (OUT / path).write_text(render(path, title, desc, body), encoding="utf-8")
    today = datetime.date.today().isoformat()
    urls = "".join(f"<url><loc>{SITE}/{'' if p == 'index.html' else p}</loc><lastmod>{today}</lastmod></url>"
                   for p, *_ in PAGES if p not in ("404.html",))
    (OUT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    for extra in ("netlify.toml", "_headers"):
        if Path(extra).exists():
            shutil.copy(extra, OUT / extra)
    print(f"built {len(PAGES)} pages into {OUT}/")


if __name__ == "__main__":
    main()
