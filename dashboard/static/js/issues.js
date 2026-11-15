/* Client-side filtering for the rendered issue register. */
(function () {
  "use strict";

  function field(section, name) {
    var items = section.querySelectorAll("li");
    for (var i = 0; i < items.length; i += 1) {
      var strong = items[i].querySelector("strong");
      if (!strong) continue;
      var label = strong.textContent.replace(":", "").trim().toLowerCase();
      if (label === name.toLowerCase()) {
        return items[i].textContent.replace(strong.textContent, "").replace(/^:\s*/, "").trim();
      }
    }
    return "";
  }

  window.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("issues-root");
    if (!root) return;
    var headings = root.querySelectorAll("h3[id^='iss-'], h3[id^='ISS-']");
    var sections = [];
    headings.forEach(function (heading) {
      var section = document.createElement("section");
      section.className = "issue-section";
      section.id = heading.id;
      heading.parentNode.insertBefore(section, heading);
      var node = heading;
      while (node) {
        var next = node.nextSibling;
        if (node !== heading && node.nodeType === 1 && /^H[23]$/.test(node.tagName)) break;
        section.appendChild(node);
        node = next;
      }
      var id = (heading.textContent.match(/ISS-\d+/i) || [heading.id])[0].toUpperCase();
      section.dataset.issue = id;
      section.dataset.severity = field(section, "Severity");
      section.dataset.category = field(section, "Category");
      section.dataset.status = field(section, "Status");
      section.dataset.search = section.textContent.toLowerCase();
      sections.push(section);
      heading.removeAttribute("id");
    });

    var severity = document.getElementById("issue-severity");
    var category = document.getElementById("issue-category");
    var status = document.getElementById("issue-status");
    var search = document.getElementById("issue-search");
    var count = document.getElementById("issue-count");
    var reset = document.getElementById("issue-reset");
    if (!severity || !category || !status) return;

    function fill(select, name) {
      var values = [];
      sections.forEach(function (section) {
        var value = section.dataset[name] || "";
        if (value && values.indexOf(value) === -1) values.push(value);
      });
      values.sort();
      values.forEach(function (value) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
    }
    fill(severity, "severity");
    fill(category, "category");
    fill(status, "status");

    function apply() {
      var sv = severity.value.toLowerCase();
      var cat = category.value.toLowerCase();
      var st = status.value.toLowerCase();
      var needle = (search ? search.value : "").toLowerCase();
      var visible = 0;
      sections.forEach(function (section) {
        var ok = true;
        if (sv && section.dataset.severity.toLowerCase() !== sv) ok = false;
        if (cat && section.dataset.category.toLowerCase() !== cat) ok = false;
        if (st && section.dataset.status.toLowerCase() !== st) ok = false;
        if (needle && section.dataset.search.indexOf(needle) === -1) ok = false;
        section.hidden = !ok;
        if (ok) visible += 1;
        var toc = document.querySelector('.toc a[href="#' + section.id + '"]');
        if (toc) toc.hidden = !ok;
      });
      document.querySelectorAll(".markdown tbody tr").forEach(function (row) {
        var id = (row.cells[0] ? row.cells[0].textContent : "").trim().toUpperCase();
        if (!/^ISS-\d+/.test(id)) return;
        var target = sections.find(function (s) { return s.dataset.issue === id; });
        row.hidden = !!(target && target.hidden);
      });
      if (count) count.textContent = "showing " + visible + " of " + sections.length + " detailed issues";
    }

    [severity, category, status].forEach(function (el) { el.addEventListener("change", apply); });
    if (search) {
      var timer = null;
      search.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(apply, 120);
      });
    }
    if (reset) {
      reset.addEventListener("click", function () {
        severity.value = "";
        category.value = "";
        status.value = "";
        if (search) search.value = "";
        apply();
      });
    }
    apply();
  });
})();
