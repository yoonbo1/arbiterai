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

  // Contact / demo form. Works with Netlify Forms out of the box; swap action for Formspree if not on Netlify.
  var form = document.querySelector('form[data-demo-form]');
  if (form) {
    form.addEventListener('submit', function (e) {
      var honeypot = form.querySelector('[name="company-site"]');
      if (honeypot && honeypot.value) { e.preventDefault(); return; }
      var btn = form.querySelector('button[type="submit"]');
      if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      if (form.hasAttribute('data-ajax')) {
        e.preventDefault();
        fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } })
          .then(function (r) { if (!r.ok) throw new Error('bad status'); form.style.display = 'none';
            var ok = document.querySelector('.form-ok'); if (ok) ok.style.display = 'block'; })
          .catch(function () { if (btn) { btn.disabled = false; btn.textContent = 'Request a demo'; }
            alert('Something went wrong. Email hello@arbiterai.tech and we will reply within one business day.'); });
      }
    });
  }

  // Current-year in footer
  document.querySelectorAll('[data-year]').forEach(function (el) { el.textContent = new Date().getFullYear(); });
})();
