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
4. Add an `og-image.png` (1200×630) to `assets/`; the template already references it.
5. Replace the placeholders: dates in privacy/terms, governing law, team bios on About,
   pricing figures once confirmed, attestation statuses on Security.

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
