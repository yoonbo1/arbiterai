# arbiterai.tech — marketing site

Static, dependency-free site. Ten pages, one stylesheet, one small script. Built by `build.py`
so the header, footer, and metadata live in one place.

```
build.py           shell template + build (python3 build.py → public/)
pages.py           page registry, pricing, docs, about, contact, legal, 404
pages_home.py      home page and the "chain of custody" ledger component
pages_product.py   product and security pages
assets/            styles.css, main.js, logo.svg, favicon.svg
netlify.toml       Netlify build + 404 redirect
vercel.json        Vercel build config
_headers           security headers (Netlify/Cloudflare Pages format)
```

## Deploy in 15 minutes

1. Push this folder to a Git repo.
2. **Netlify** (recommended: forms work with zero setup): New site → import repo → build command
   `python3 build.py`, publish directory `public`. Enable Forms in the site settings.
   **Vercel**: import repo; `vercel.json` is already configured. Point the contact form at a
   Formspree/Basin endpoint and add `data-ajax` to the `<form>` tag.
   **Cloudflare Pages / GitHub Pages**: run `python3 build.py` in CI and publish `public/`.
3. Add the custom domain `arbiterai.tech` (and `www`) in the host dashboard. At your registrar
   set the A/ALIAS record for the apex and a CNAME for `www` as the host instructs. HTTPS is automatic.
4. ~~Add an `og-image.png` (1200×630) to `assets/`~~ — done; see `assets/og-image.png`.
5. Replace the placeholders: dates in privacy/terms, governing law, team bios on About,
   pricing figures once confirmed, attestation statuses on Security.

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
lives on `www` and the apex forwards to it. Both are configured and verified.

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
  So `arbiterai.tech/product.html` redirecting while `arbiterai.tech/` does not is expected
  during that window, not a misconfiguration.
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

## Launch checklist

**Domain and email**
- [ ] DNS pointed, HTTPS live, `www` redirects to apex
- [ ] `hello@arbiterai.tech` mailbox exists (Google Workspace or Fastmail); SPF, DKIM, DMARC records set
- [ ] `security@` alias for disclosures; add a `/.well-known/security.txt`

**Lead capture**
- [ ] Contact form tested end to end; notifications go to a shared inbox or CRM
- [ ] Autoresponder: "we reply within one business day" and the no-PHI reminder
- [ ] Calendar link (Cal.com / Calendly) in the autoresponder for scoping calls

**Analytics and SEO**
- [ ] Privacy-respecting analytics (Plausible, Fathom, or Cloudflare Web Analytics): one script tag in `build.py`, then add its domain to the CSP in `_headers`
- [ ] Submit `sitemap.xml` in Google Search Console and Bing Webmaster Tools
- [ ] Verify Organization schema with Google's Rich Results test

**Legal and trust**
- [ ] Counsel reviews privacy policy and terms
- [ ] BAA template ready to send (from counsel, or a reputable healthcare-law template reviewed by counsel)
- [ ] NDA template for the security package
- [ ] Security page reflects only attestations you actually hold

**Sales assets** (link from the site or send after calls)
- [ ] One-page shared-responsibility sheet (PDF export of the Security page table)
- [ ] Pilot proposal template with scope, acceptance criteria, price
- [ ] 3-minute recorded demo on synthetic data
- [ ] Architecture diagram PDF

**Before claiming anything publicly**
- Do not say "HIPAA certified" — there is no such certification. Say "HIPAA-ready", "built for HIPAA compliance", "we sign a BAA".
- Do not publish SOC 2 or HITRUST claims until the report exists.
- Keep the "no medical advice" line in the footer and terms.

## Editing

Copy lives in `pages*.py` as HTML strings. Colors and type are CSS variables at the top of
`assets/styles.css`. Navigation is the `NAV` list in `build.py`. Run `python3 build.py`
after any change; the host rebuilds automatically on push.
