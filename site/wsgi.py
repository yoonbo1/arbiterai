"""Heroku entry point for the arbiterai.tech marketing site.

The site is static. build.py generates public/, which is NOT committed, so bin/post_compile
runs the build during slug compilation. WhiteNoise serves the result; anything that matches
no file falls through to the generated 404 page.

Two things are not static:

* Security headers, applied here because _headers is read only by Netlify and Cloudflare
  Pages, and vercel.json only by Vercel. Same policy, one place per host.
* The demo request form. It POSTs to /submit, handled below: honeypot check, validation,
  then forward to FORM_ENDPOINT. Forwarding happens server side, so the browser only ever
  talks to this origin and the CSP needs no third-party connect-src.
* Canonical host redirect. Both arbiterai.tech and www.arbiterai.tech point here; requests
  for the non-canonical one are redirected so there is a single indexable host. This is done
  in the app rather than at the DNS provider because Squarespace's domain forwarding serves
  its own parking page at the root path and only forwards deeper paths.
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from whitenoise import WhiteNoise

log = logging.getLogger("arbiter.site")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

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


# ------------------------------------------------------------- canonical host redirect
# Everything the site advertises (canonical, og:url, sitemap) uses this origin, so any other
# host that resolves here is redirected to it. herokuapp.com is left alone so the app's own
# URL stays usable for smoke tests.
CANONICAL_HOST = urllib.parse.urlsplit(
    os.environ.get("SITE_URL", "https://www.arbiterai.tech")).netloc.lower()


def _canonical_redirect(environ):
    """Return the URL to redirect to, or None to serve normally."""
    host = (environ.get("HTTP_HOST") or "").split(":")[0].lower()
    if not host or host == CANONICAL_HOST or host.endswith(".herokuapp.com"):
        return None
    path = environ.get("PATH_INFO", "/")
    query = environ.get("QUERY_STRING", "")
    return f"https://{CANONICAL_HOST}{path}" + (f"?{query}" if query else "")


# ---------------------------------------------------------------- demo request form
FORM_PATH = "/submit"
# Where submissions go: a Formspree/Basin/webhook URL that accepts a JSON POST. When unset,
# submissions are written to the application log so nothing is silently lost. That is a
# stopgap, not lead capture: logs are not durable and are a poor place for personal data.
FORM_ENDPOINT = os.environ.get("FORM_ENDPOINT", "").strip()
FORM_FIELDS = ("name", "email", "org", "role", "interest", "volume", "hosting", "message", "consent")
REQUIRED_FIELDS = ("name", "email", "org", "consent")
HONEYPOT = "company-site"
MAX_BODY = 64 * 1024


def _redirect(start_response, location):
    start_response("303 See Other",
                   [("Location", location), ("Content-Length", "0"), *SECURITY_HEADERS.items()])
    return [b""]


def _json(start_response, status, payload):
    body = json.dumps(payload).encode()
    start_response(status, [("Content-Type", "application/json"),
                            ("Content-Length", str(len(body))), *SECURITY_HEADERS.items()])
    return [body]


def _reply(start_response, wants_json, ok_status, redirect_to, payload):
    if wants_json:
        return _json(start_response, ok_status, payload)
    return _redirect(start_response, redirect_to)


def _forward(fields):
    """POST the submission to FORM_ENDPOINT. Raises on failure so the caller can tell the
    visitor to email instead, rather than showing a success page for a lost lead."""
    req = urllib.request.Request(
        FORM_ENDPOINT, data=json.dumps(fields).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        if r.status >= 300:
            raise urllib.error.HTTPError(FORM_ENDPOINT, r.status, "bad status", r.headers, None)


def _handle_submit(environ, start_response):
    wants_json = "application/json" in environ.get("HTTP_ACCEPT", "")
    try:
        size = min(int(environ.get("CONTENT_LENGTH") or 0), MAX_BODY)
    except ValueError:
        size = 0
    raw = environ["wsgi.input"].read(size).decode("utf-8", "replace") if size else ""
    posted = urllib.parse.parse_qs(raw, keep_blank_values=True)

    def get(key):
        return (posted.get(key, [""])[0] or "").strip()

    # Bots fill hidden fields. Accept silently so they do not learn they were caught.
    if get(HONEYPOT):
        log.info("form: honeypot triggered, dropped")
        return _reply(start_response, wants_json, "200 OK", "/contact.html?sent=1", {"ok": True})

    missing = [f for f in REQUIRED_FIELDS if not get(f)]
    if missing or "@" not in get("email"):
        log.info("form: rejected, missing or invalid %s", missing or ["email"])
        return _reply(start_response, wants_json, "422 Unprocessable Entity",
                      "/contact.html?error=1", {"ok": False, "missing": missing})

    fields = {f: get(f) for f in FORM_FIELDS if get(f)}
    if not FORM_ENDPOINT:
        log.warning("form: FORM_ENDPOINT unset, logging submission instead: %s",
                    json.dumps(fields, sort_keys=True))
        return _reply(start_response, wants_json, "200 OK", "/contact.html?sent=1", {"ok": True})
    try:
        _forward(fields)
    except Exception as e:
        # Log the payload so the lead is recoverable, then tell the visitor honestly.
        log.error("form: forwarding failed (%s); submission: %s",
                  type(e).__name__, json.dumps(fields, sort_keys=True))
        return _reply(start_response, wants_json, "502 Bad Gateway",
                      "/contact.html?error=1", {"ok": False})
    log.info("form: forwarded a submission")
    return _reply(start_response, wants_json, "200 OK", "/contact.html?sent=1", {"ok": True})


def _not_found(environ, start_response):
    """Everything WhiteNoise could not serve. Netlify does this with a redirect rule."""
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
    """WhiteNoise answers GET/HEAD for the generated files. Two things come first: the
    canonical host redirect, and the form POST, because WhiteNoise rejects any non-GET
    method with 405."""
    target = _canonical_redirect(environ)
    if target:
        start_response("301 Moved Permanently",
                       [("Location", target), ("Content-Length", "0"), *SECURITY_HEADERS.items()])
        return [b""]
    if environ.get("PATH_INFO") == FORM_PATH:
        if environ.get("REQUEST_METHOD") == "POST":
            return _handle_submit(environ, start_response)
        return _redirect(start_response, "/contact.html")
    return _static(environ, start_response)


if not FORM_ENDPOINT:
    log.warning("FORM_ENDPOINT is unset: demo requests will only reach this log. "
                "Set it to a Formspree/Basin/webhook URL for durable lead capture.")
