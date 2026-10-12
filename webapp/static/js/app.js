// Shared page behaviour for every page: header menus, toasts, loading
// feedback, KPI count-up, the save celebration and the Home card tilt.
// Purely presentational — no form field, URL or payload is changed here.
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Flash messages that mean "an entry was saved" — they get the celebration.
  var CELEBRATE = /^(Saved|Updated|Filled|Created|Added a new row)/;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  // ready() can run synchronously (this script is deferred), so everything it
  // uses must already be defined above. Each step is isolated: a failure in a
  // cosmetic one (icons, confetti) must never stop the delete confirmations.
  ready(function () {
    [
      function () { if (window.lucide) window.lucide.createIcons(); },
      initConfirms, initMenus, initToasts, initLoading, initCountUp, initTilt,
    ].forEach(function (step) {
      try { step(); } catch (err) { if (window.console) console.error(err); }
    });
  });

  // --- Header: section switcher (desktop) and hamburger panel (mobile) -------
  function initMenus() {
    var switcher = document.getElementById("sectionSwitcher");
    var menuBtn = document.getElementById("menuButton");
    var menu = document.getElementById("mobileMenu");

    function setMenu(open) {
      if (!menu) return;
      menu.hidden = !open;
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
      // The icons are <svg> by now (Lucide), where .hidden isn't the attribute.
      menuBtn.querySelector("[data-open]").toggleAttribute("hidden", open);
      menuBtn.querySelector("[data-close]").toggleAttribute("hidden", !open);
      menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    }
    if (menuBtn) menuBtn.addEventListener("click", function () { setMenu(menu.hidden); });

    document.addEventListener("click", function (e) {
      if (switcher && switcher.open && !switcher.contains(e.target)) switcher.open = false;
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (switcher) switcher.open = false;
      if (menu && !menu.hidden) { setMenu(false); menuBtn.focus(); }
    });
  }

  // --- Toasts: slide in, auto-dismiss, celebrate a successful save ---------

  function initToasts() {
    var celebrated = false;
    document.querySelectorAll(".toast").forEach(function (toast, i) {
      requestAnimationFrame(function () {
        toast.classList.remove("opacity-0", "translate-x-4");
      });
      var dismiss = function () {
        toast.classList.add("opacity-0", "translate-x-4");
        setTimeout(function () { toast.remove(); }, 300);
      };
      var timer = setTimeout(dismiss, 5000 + i * 600);
      var close = toast.querySelector(".toast-close");
      if (close) close.addEventListener("click", function () { clearTimeout(timer); dismiss(); });

      var text = (toast.querySelector("p") || toast).textContent.trim();
      if (!celebrated && toast.dataset.category === "ok" && CELEBRATE.test(text)) {
        celebrated = true;
        toast.classList.add("shine");
        celebrate();
      }
    });
  }

  // A short burst of gold confetti from the top of the screen.
  function celebrate() {
    if (reduceMotion) return;
    var canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:60";
    document.body.appendChild(canvas);
    var ctx = canvas.getContext("2d");
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = (canvas.width = innerWidth * dpr);
    var h = (canvas.height = innerHeight * dpr);
    var colors = ["#E4BE63", "#C9962B", "#F6EBCB", "#A97B1F", "#FFFFFF", "#1F3157"];
    var count = innerWidth < 640 ? 70 : 140;
    var parts = [];
    for (var i = 0; i < count; i++) {
      parts.push({
        x: w * (0.2 + Math.random() * 0.6), y: -20 * dpr - Math.random() * h * 0.2,
        vx: (Math.random() - 0.5) * 6 * dpr, vy: (2 + Math.random() * 4) * dpr,
        size: (4 + Math.random() * 5) * dpr, rot: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.3,
        color: colors[i % colors.length], round: Math.random() < 0.3,
      });
    }
    var start = performance.now();
    (function frame(now) {
      var t = now - start;
      ctx.clearRect(0, 0, w, h);
      ctx.globalAlpha = Math.max(0, 1 - Math.max(0, t - 1400) / 600);
      parts.forEach(function (p) {
        p.vy += 0.12 * dpr; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.rot += p.vr;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.fillStyle = p.color;
        if (p.round) { ctx.beginPath(); ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2); ctx.fill(); }
        else ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
        ctx.restore();
      });
      if (t < 2000) requestAnimationFrame(frame);
      else canvas.remove();
    })(start);
  }

  // --- Delete confirmations (forms carrying data-confirm) -------------------
  function initConfirms() {
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (!confirm(form.dataset.confirm)) e.preventDefault();
      });
    });
  }

  // --- Loading feedback: top progress bar + busy submit button -------------
  function initLoading() {
    var bar = document.getElementById("navProgress");
    function start() { if (bar) bar.classList.add("run"); }

    document.addEventListener("click", function (e) {
      var a = e.target.closest("a[href]");
      if (!a || e.defaultPrevented || e.button !== 0) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (a.target === "_blank" || a.origin !== location.origin) return;
      if (a.getAttribute("href").charAt(0) === "#") return;
      start();
    });

    // Bubble phase on document: every page's own validation/confirm handler
    // has already run, so a cancelled submit is never shown as "saving".
    document.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      start();
      var btn = e.target.querySelector("button[type=submit][data-busy]");
      if (btn) {
        // Defer, so the browser has already collected the form data.
        setTimeout(function () {
          btn.disabled = true;
          btn.dataset.label = btn.innerHTML;
          btn.innerHTML = '<svg class="spin h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
            '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity=".25" stroke-width="3"/>' +
            '<path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg> ' +
            btn.dataset.busy;
        }, 0);
      }
    });

    // Coming back via the back button restores the page from cache: reset it.
    window.addEventListener("pageshow", function (e) {
      if (!e.persisted) return;
      if (bar) bar.classList.remove("run");
      document.querySelectorAll("button[data-label]").forEach(function (b) {
        b.disabled = false; b.innerHTML = b.dataset.label;
      });
    });
  }

  // --- KPI count-up: animates the first number inside [data-countup] -------
  function initCountUp() {
    var els = document.querySelectorAll("[data-countup]");
    if (reduceMotion || !els.length) return;
    els.forEach(function (el) {
      var text = el.textContent;
      var m = text.match(/-?[\d,]*\.?\d+/);
      if (!m) return;
      var raw = m[0];
      var target = parseFloat(raw.replace(/,/g, ""));
      if (!isFinite(target) || target === 0) return;
      var decimals = (raw.split(".")[1] || "").length;
      var commas = raw.indexOf(",") !== -1;
      var before = text.slice(0, m.index), after = text.slice(m.index + raw.length);
      // Same grouping as the server's "{:,}" formatting (1,234,567).
      var fmt = function (v) {
        var s = commas
          ? v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
          : v.toFixed(decimals);
        return before + s + after;
      };
      var t0 = null, dur = 900;
      el.textContent = fmt(0);
      requestAnimationFrame(function step(now) {
        if (t0 === null) t0 = now;
        var p = Math.min(1, (now - t0) / dur);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = p < 1 ? fmt(target * eased) : text;
        if (p < 1) requestAnimationFrame(step);
      });
    });
  }

  // --- Home: 3D tilt of the section cards toward the pointer ---------------
  function initTilt() {
    if (reduceMotion || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    document.querySelectorAll(".tilt").forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var r = card.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width - 0.5;
        var y = (e.clientY - r.top) / r.height - 0.5;
        card.style.setProperty("--ry", (x * 10).toFixed(2) + "deg");
        card.style.setProperty("--rx", (-y * 8).toFixed(2) + "deg");
      });
      card.addEventListener("pointerleave", function () {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
      });
    });
  }
})();
