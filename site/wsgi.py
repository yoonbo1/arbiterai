"""Heroku entry point for the arbiterai.tech marketing site.

The site is static. build.py generates public/, which is NOT committed, so bin/post_compile
runs the build during slug compilation. WhiteNoise serves the result; anything that matches
no file falls through to the generated 404 page.

Security headers are applied here because _headers is read only by Netlify and Cloudflare
Pages, and vercel.json only by Vercel. Same policy, one place per host.
"""
import os
from pathlib import Path

from whitenoise import WhiteNoise

PUBLIC = Path(__file__).parent / "public"

# Mirrors _headers. HSTS without `preload`: preloading is a one-way commitment that is hard
# to undo, so opt in deliberately once the domain is settled.
CSP = ("default-src 'self'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; "
       "img-src 'self' data:; "
       "script-src 'self'; "
       "form-action 'self' https://formspree.io; "
       "frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": CSP,
}


def _add_headers(headers, path, url):
    for key, value in SECURITY_HEADERS.items():
        headers[key] = value


def _not_found(environ, start_response):
    """Everything WhiteNoise could not serve. Netlify does this with a redirect rule."""
    page = PUBLIC / "404.html"
    body = page.read_bytes() if page.exists() else b"<h1>Page not found</h1>"
    start_response("404 Not Found",
                   [("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                    *SECURITY_HEADERS.items()])
    return [body]


app = WhiteNoise(
    _not_found,
    root=str(PUBLIC),
    index_file=True,                                  # / -> index.html
    autorefresh=bool(os.environ.get("SITE_AUTOREFRESH")),   # set it for local editing
    add_headers_function=_add_headers,
)
