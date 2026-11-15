/* Shared, dependency-free UI behaviour. */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  ready(function () {
    var sidebar = document.getElementById("sidebar");
    var toggle = document.getElementById("nav-toggle");
    var scrim = document.getElementById("scrim");

    function setNav(open) {
      if (!sidebar || !toggle) return;
      sidebar.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (scrim) scrim.hidden = !open;
    }

    if (toggle) {
      toggle.addEventListener("click", function () {
        setNav(!sidebar.classList.contains("is-open"));
      });
    }
    if (scrim) {
      scrim.addEventListener("click", function () { setNav(false); });
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sidebar && sidebar.classList.contains("is-open")) {
        setNav(false);
      }
      if (event.key === "/" && !isTyping(event.target)) {
        var search = document.querySelector("input[type='search']");
        if (search) {
          event.preventDefault();
          search.focus();
        }
      }
    });

    function isTyping(target) {
      if (!target) return false;
      var tag = target.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
    }

    function copyText(text, button) {
      var done = function () {
        if (!button) return;
        var old = button.textContent;
        button.textContent = "Copied";
        button.disabled = true;
        window.setTimeout(function () {
          button.textContent = old;
          button.disabled = false;
        }, 1200);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done, function () { fallback(text, done); });
      } else {
        fallback(text, done);
      }
    }

    function fallback(text, done) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); done(); } catch (e) { /* ignore */ }
      document.body.removeChild(area);
    }

    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = document.getElementById(button.getAttribute("data-copy"));
        if (target) copyText(target.textContent, button);
      });
    });
    document.querySelectorAll("[data-copy-value]").forEach(function (button) {
      button.addEventListener("click", function () {
        copyText(button.getAttribute("data-copy-value") || "", button);
      });
    });

    // Date and altitude presets on the map filter form.
    var from = document.getElementById("date-from");
    var to = document.getElementById("date-to");
    document.querySelectorAll("[data-days]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!from || !to) return;
        var days = button.getAttribute("data-days");
        if (days === "all") {
          from.value = "";
          to.value = "";
          return;
        }
        var end = new Date();
        var start = new Date();
        start.setDate(start.getDate() - Number(days));
        from.value = start.toISOString().slice(0, 10);
        to.value = end.toISOString().slice(0, 10);
      });
    });
    var altPreset = document.getElementById("alt-preset");
    if (altPreset) {
      altPreset.addEventListener("change", function () {
        var parts = altPreset.value.split(",");
        if (parts.length !== 2) return;
        var min = document.getElementById("alt-min");
        var max = document.getElementById("alt-max");
        if (min) min.value = parts[0];
        if (max) max.value = parts[1];
      });
    }
  });
})();
