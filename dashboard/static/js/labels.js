/* Label distribution chart. Falls back to the server-rendered tables. */
(function () {
  "use strict";
  window.addEventListener("DOMContentLoaded", function () {
    var dataNode = document.getElementById("label-chart-data");
    var canvas = document.getElementById("label-chart");
    if (!dataNode || !canvas || typeof window.Chart === "undefined") return;
    var data;
    try { data = JSON.parse(dataNode.textContent); } catch (e) { return; }
    window.Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    window.Chart.defaults.color = getComputedStyle(document.body).getPropertyValue("--muted");
    new window.Chart(canvas, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          { label: "Primary", data: data.primary, backgroundColor: "#2f6fed", borderRadius: 4 },
          { label: "Combined (derived)", data: data.combined, backgroundColor: "#9aa7b4", borderRadius: 4 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
          x: { grid: { display: false } }
        },
        plugins: { legend: { position: "bottom" } }
      }
    });
  });
})();
