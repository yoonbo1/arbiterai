// Arbiter AI — minimal site JS: nav toggle, the trace card's check-off sequence, footer year.
(function () {
  var toggle = document.querySelector('.nav-toggle');
  var nav = document.querySelector('.nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // Trace card: check the ingest and query stages off in sequence once, on page load.
  var ledger = document.querySelector('.ledger[data-animate]');
  if (ledger) {
    var items = ledger.querySelectorAll('li');
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) { items.forEach(function (li) { li.classList.add('done'); }); }
    else {
      items.forEach(function (li, i) {
        setTimeout(function () { li.classList.add('done'); }, 400 + i * 420);
      });
    }
  }

  // Current year in the footer
  document.querySelectorAll('[data-year]').forEach(function (el) { el.textContent = new Date().getFullYear(); });
})();
