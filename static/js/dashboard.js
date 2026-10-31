/* Finance dashboard charts (Chart.js, vendored). Data comes from the #chart-data json_script. */
(function () {
  "use strict";
  const source = document.getElementById("chart-data");
  if (!source || !window.Chart) return;
  const data = JSON.parse(source.textContent);
  const styles = getComputedStyle(document.documentElement);
  const primary = styles.getPropertyValue("--bl-primary").trim() || "#4f46e5";
  const currency = document.body.dataset.currency || "";
  const money = (value) => currency + Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.maintainAspectRatio = false;

  const revenue = document.getElementById("revenue-chart");
  if (revenue) {
    new Chart(revenue, {
      type: "bar",
      data: {
        labels: data.months,
        datasets: [
          { label: "Invoiced", data: data.invoiced, backgroundColor: primary, borderRadius: 6 },
          { label: "Collected", data: data.collected, backgroundColor: "#10b981", borderRadius: 6 },
        ],
      },
      options: {
        scales: { y: { beginAtZero: true, ticks: { callback: money } } },
        plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${money(ctx.parsed.y)}` } } },
      },
    });
  }

  const status = document.getElementById("status-chart");
  if (status) {
    new Chart(status, {
      type: "doughnut",
      data: {
        labels: data.statusLabels,
        datasets: [{ data: data.statusCounts, backgroundColor: ["#94a3b8", "#3b82f6", "#6366f1", "#10b981", "#f59e0b", "#334155"] }],
      },
      options: { plugins: { legend: { position: "bottom" } }, cutout: "62%" },
    });
  }

  const plans = document.getElementById("plan-chart");
  if (plans) {
    new Chart(plans, {
      type: "bar",
      data: { labels: data.planLabels, datasets: [{ label: "MRR", data: data.planMrr, backgroundColor: primary, borderRadius: 6 }] },
      options: {
        indexAxis: "y",
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => money(ctx.parsed.x) } } },
        scales: { x: { beginAtZero: true, ticks: { callback: money } } },
      },
    });
  }
})();
