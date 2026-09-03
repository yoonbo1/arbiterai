// Arbiter AI — minimal site JS: nav toggle, hero ledger sequence, contact form handling.
(function () {
  var toggle = document.querySelector('.nav-toggle');
  var nav = document.querySelector('.nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // Custody ledger: check off stages in sequence once, on page load.
  var ledger = document.querySelector('.ledger[data-animate]');
  if (ledger) {
    var items = ledger.querySelectorAll('li');
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) { items.forEach(function (li) { li.classList.add('done'); }); }
    else {
      items.forEach(function (li, i) {
        setTimeout(function () { li.classList.add('done'); }, 500 + i * 550);
      });
    }
  }

  // Contact / demo form. Posts to /submit, which the site's WSGI app handles (see wsgi.py).
  // Without JS the same POST still works and the server redirects back with ?sent=1.
  var form = document.querySelector('form[data-demo-form]');
  function showPanel(sel) {
    var el = document.querySelector(sel);
    if (el) { el.style.display = 'block'; }
    if (form && sel === '.form-ok') { form.style.display = 'none'; }
  }
  // Server-side (no-JS) round trip lands back here with a query flag.
  if (/[?&]sent=1/.test(location.search)) { showPanel('.form-ok'); }
  if (/[?&]error=1/.test(location.search)) { showPanel('.form-error'); }

  if (form) {
    form.addEventListener('submit', function (e) {
      var honeypot = form.querySelector('[name="company-site"]');
      if (honeypot && honeypot.value) { e.preventDefault(); return; }
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      if (form.hasAttribute('data-ajax')) {
        e.preventDefault();
        // URLSearchParams sends application/x-www-form-urlencoded, which the handler parses.
        fetch(form.action, {
          method: 'POST',
          body: new URLSearchParams(new FormData(form)),
          headers: { Accept: 'application/json' }
        })
          .then(function (r) { if (!r.ok) throw new Error('bad status'); showPanel('.form-ok'); })
          .catch(function () { if (btn) { btn.disabled = false; btn.textContent = 'Request a demo'; }
            showPanel('.form-error'); });
      }
    });
  }

  // Current-year in footer
  document.querySelectorAll('[data-year]').forEach(function (el) { el.textContent = new Date().getFullYear(); });
})();
