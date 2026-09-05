"""Heroku entry point for the arbiterai.tech site.

The site is static. build.py generates public/, which is NOT committed, so bin/post_compile
runs the build during slug compilation. WhiteNoise serves the result; anything that matches
no file falls through to the generated 404 page.

Three things are not static:

* Security headers, applied here. Heroku has no static-host header file, so the policy
  lives in this one place.
* Canonical host redirect. Both arbiterai.tech and www.arbiterai.tech point here; requests
  for the non-canonical one are redirected so there is a single indexable host. This is done
  in the app rather than at the DNS provider because Squarespace's domain forwarding serves
  its own parking page at the root path and only forwards deeper paths.
* Permanent redirects for the two paths that went away when the site was repositioned as a
  reference implementation: /product.html became /how-it-works.html, and the plans page is
  gone, so it goes to the home page.
"""
import os
import urllib.parse
from pathlib import Path

from whitenoise import WhiteNoise

PUBLIC = Path(__file__).parent / "public"

# HSTS without `preload`: preloading is a one-way commitment that is hard
# to undo, so opt in deliberately once the domain is settled.
CSP = ("default-src 'self'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; "
       "img-src 'self' data:; "
       "script-src 'self'; "
       "form-action 'none'; "
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


# ------------------------------------------------------------- canonical host redirect
# Everything the site advertises (canonical, og:url, sitemap) uses this origin, so any other
# host that resolves here is redirected to it. herokuapp.com is left alone so the app's own
# URL stays usable for smoke tests, and so are loopback hosts, so `make serve-site` and the
# preview config serve the local build instead of bouncing the browser to production.
CANONICAL_HOST = urllib.parse.urlsplit(
    os.environ.get("SITE_URL", "https://www.arbiterai.tech")).netloc.lower()


def _canonical_redirect(environ):
    """Return the URL to redirect to, or None to serve normally."""
    host = (environ.get("HTTP_HOST") or "").split(":")[0].lower()
    if (not host or host == CANONICAL_HOST or host.endswith(".herokuapp.com")
            or host in ("localhost", "127.0.0.1")):
        return None
    path = environ.get("PATH_INFO", "/")
    query = environ.get("QUERY_STRING", "")
    return f"https://{CANONICAL_HOST}{path}" + (f"?{query}" if query else "")


# ------------------------------------------------------------------ retired paths
# Inbound links and search results may still carry these. Path only: the query string is
# dropped on purpose, because the old ?plan= variants mean nothing any more.
REDIRECTS = {
    "/pricing.html": "/",
    "/product.html": "/how-it-works.html",
}


def _permanent_redirect(start_response, location):
    start_response("301 Moved Permanently",
                   [("Location", location), ("Content-Length", "0"), *SECURITY_HEADERS.items()])
    return [b""]


def _not_found(environ, start_response):
    """Everything WhiteNoise could not serve."""
    page = PUBLIC / "404.html"
    body = page.read_bytes() if page.exists() else b"<h1>Page not found</h1>"
    start_response("404 Not Found",
                   [("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                    *SECURITY_HEADERS.items()])
    return [body]


_static = WhiteNoise(
    _not_found,
    root=str(PUBLIC),
    index_file=True,                                  # / -> index.html
    autorefresh=bool(os.environ.get("SITE_AUTOREFRESH")),   # set it for local editing
    add_headers_function=_add_headers,
)


def app(environ, start_response):
    """WhiteNoise answers GET/HEAD for the generated files. The two redirects come first:
    the canonical host, then the retired paths."""
    target = _canonical_redirect(environ)
    if target:
        return _permanent_redirect(start_response, target)
    location = REDIRECTS.get(environ.get("PATH_INFO", ""))
    if location:
        return _permanent_redirect(start_response, location)
    return _static(environ, start_response)
