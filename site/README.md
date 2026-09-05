# arbiterai.tech — site

Static, dependency-free site for the Arbiter AI reference implementation. One stylesheet,
one small script, no forms. Built by `build.py` so the header, footer and metadata live in
one place.

```
build.py           shell template, NAV, the positioning strings (ONE_LINER, SHORT), build
                   (python3 build.py → public/, sitemap.xml, robots.txt, feed.xml)
pages.py           page registry (PAGES), docs, about, contact, privacy, terms, 404
pages_home.py      home page and the trace card (a real ingest + query trace for synthetic
                   record P00001, reused on the How-it-works page)
pages_product.py   How it works (how-it-works.html) and Security model (security.html)
pages_blog.py      blog index, post metadata (POSTS) and article bodies
assets/            styles.css, main.js, logo.svg, favicon.svg, og-image.png, article PDF
wsgi.py            Heroku entry point: WhiteNoise, security headers, canonical-host redirect,
                   301s for the retired /pricing.html and /product.html, 404 fallback
Procfile, bin/     gunicorn command; bin/post_compile runs build.py during the slug build
```

## Pages

| Path | What it is |
|---|---|
| `/` | Hero (H1, the one-liner), the four properties with where each is enforced and tested, six use cases the implementation covers, the benchmarks table, four failure-mode teasers linking to the post-mortems, author strip |
| `/how-it-works.html` | The pipeline, stage by stage: what it does, which module it lives in, which test or eval covers it. Why an arbiter; routing cost as an engineering note; the two endpoints; per-job cost accounting |
| `/security.html` | Five numbered invariants (enforced / tested), the superuser finding, the honest scope statement, what else is and is not in the code |
| `/docs.html` | Run it locally, run the evals (`#evals`: what each metric means, adding gold questions), data (all synthetic; pointing the harness at i2b2 2014), API (`#api`), concepts, errors |
| `/blog.html`, `/blog/*.html` | Index and posts, from `pages_blog.py` |
| `/about.html` | Who built it, why, what it is not, links |
| `/contact.html` | Email and GitHub profile. No form |
| `/privacy.html`, `/terms.html` | Website-only legal pages |
| `/404.html` | Served by `wsgi.py` for any unmatched path |

`/pricing.html` and `/product.html` no longer exist; `wsgi.py` 301s them to `/` and
`/how-it-works.html` (path only, query string dropped). Nothing links to them.

## Voice and claims

First person singular, engineer to engineer. Every claim on the site points at a code path,
a test name, an eval metric or a post. The repository is private for now, so code paths are
rendered as `<code>`, not links, and the phrase is "open reference implementation", never
"open-source". The one-liner and the short form are constants in `build.py`; the honest
scope statement on the security page is verbatim from the repositioning brief. Do not add
certification, SLA, support or BAA language anywhere.

## Deploy

Heroku only; the next section has the app, the build hook and DNS. `wsgi.py` applies the
security headers, redirects the non-canonical host and the two retired paths, and serves the
404 page. If you ever move hosts: run `python3 build.py` in that host's CI, publish
`public/`, and reproduce those three things in the new host's own configuration.

## Heroku (current deployment)

The site runs on Heroku as `arbiterai-site`, served by gunicorn + WhiteNoise from `wsgi.py`.
`public/` is generated during the build by `bin/post_compile`, so it is never committed.

```bash
make serve-site                          # same stack locally on http://127.0.0.1:8765
git subtree push --prefix site heroku main   # or: make deploy-site
heroku logs --tail -a arbiterai-site
```

`SITE_URL` is a config var and sets the canonical origin baked into `<link rel=canonical>`,
`og:url` and `sitemap.xml`. It is `https://www.arbiterai.tech`.

### DNS at Squarespace (live)

Heroku publishes no static IPs, so the apex cannot point at it with A records. The site
lives on `www` and the apex forwards to it. Both are configured and verified; the apex
forwarding activated on 2026-09-04.

| Where | Type | Host | Value |
|---|---|---|---|
| Custom records | CNAME | `www` | `protected-sinraptor-hr8yljyysuen6z4bu4ylvvf1.herokudns.com` (TTL 30 min) |
| Website → Domain Forwarding | 301 | `@` | `https://www.arbiterai.tech`, path forwarded |

Two things to know if you ever redo this:

- In the forwarding dialog the subdomain box already appends `.arbiterai.tech`, so the root
  domain is entered as `@`. Typing the full domain creates a rule for
  `arbiterai.tech.arbiterai.tech`, which does nothing.
- Saving a forwarding rule deletes the "Squarespace Defaults" preset, which is what removes
  the conflicting `www` CNAME to `ext-sq.squarespace.com`. Do the forwarding rule first, then
  add the `www` CNAME. Squarespace then manages its own apex A records under a "Squarespace
  Domain Forwarding" preset. The Email Security preset (SPF, DMARC, DKIM) is untouched.

Two things about the apex that cost time, so they are written down:

- **Squarespace forwarding takes 24 to 48 hours to activate**, and its own dialog says so
  only after you save. Deeper paths start forwarding well before the root does, and until
  the root activates Squarespace's CDN keeps serving the "Coming Soon" parking page there.
- **An ALIAS record at the apex is not available on this zone.** Squarespace offers the
  record type, but rejects it with "ALIAS records are not allowed on a zone using DNSSEC",
  and DNSSEC is enabled for arbiterai.tech. Pointing the bare apex straight at Heroku
  therefore needs either DNSSEC switched off, which is a deliberate security decision, or
  DNS moved to a provider that does both, such as Cloudflare with CNAME flattening.

`wsgi.py` redirects any non-canonical host to `SITE_URL`, so if the apex is ever pointed at
Heroku the redirect is already in place and only `heroku domains:add arbiterai.tech` is needed.

Heroku's Automated Certificate Management issued the Let's Encrypt certificate for
`www.arbiterai.tech` a few minutes after the CNAME went live. Check with
`heroku certs:auto -a arbiterai-site`. There are no CAA records blocking issuance.

## Checklist

- [x] DNS pointed, HTTPS live, apex forwards to `www`
- [ ] `hello@arbiterai.tech` mailbox exists; SPF, DKIM, DMARC records set
- [ ] Submit `sitemap.xml` in Google Search Console and Bing Webmaster Tools
- [ ] Verify the Organization schema with Google's Rich Results test
- [ ] Add the GitHub repository link (hero button, footer, author strip) once the repo is public
- [ ] Add the i2b2 2014 row's value to the benchmarks table once the harness has been run on it
- Keep the "no medical advice" line in the footer and terms.
- Do not say "HIPAA certified" (there is no such certification), and do not add SOC 2 or
  HITRUST claims.

## Editing

Copy lives in `pages*.py` as HTML strings. Colors and type are CSS variables at the top of
`assets/styles.css`. Navigation is the `NAV` list in `build.py`; the footer links are in the
shell template there. Run `python3 build.py` after any change; the host rebuilds
automatically on push.

To add a blog post, append a dict to `POSTS` in `pages_blog.py` (slug, path under `blog/`,
titles, description, summary, ISO date, reading time, section, body HTML). `BLOG_PAGES`
feeds it into `PAGES`, and the index page, `sitemap.xml` (with the post's own `lastmod`),
`feed.xml`, the `BlogPosting`/`BreadcrumbList` JSON-LD and the `article:*` meta tags are all
generated from the same entry. A `PAGES` row may carry an optional fifth element, a meta
dict of `og_type`, `lastmod` and `head` (an extra `<head>` fragment where `__SITE__` is
replaced with the canonical origin).

The home page's "Failure modes I found" cards link to four post slugs by path
(`/blog/spacy-redacted-daily.html`, `/blog/deid-recall-flattering-metric.html`,
`/blog/7b-judge-citation-placement.html`, `/blog/postgres-superuser-bypasses-rls.html`);
keep those slugs stable in `POSTS`.
