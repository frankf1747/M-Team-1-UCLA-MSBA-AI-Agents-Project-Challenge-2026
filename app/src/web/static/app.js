const PIPELINE = [
  "pdf_context", "data_reconciliation", "baseline_kpis", "scenario_parser",
  "disruption_engine", "impact_analysis", "contingency_planner", "audit", "report"
];
const HANDOFF = {
  pdf_context: "Playbook rules + KPI thresholds → downstream agents",
  data_reconciliation: "Clean valid units + excluded log → KPI engine",
  baseline_kpis: "Baseline penalty / KPIs → impact comparison",
  scenario_parser: "Structured ScenarioSpec → disruption engine",
  disruption_engine: "Scenario KPIs → impact analysis",
  impact_analysis: "Quantified deltas + binding constraint → planner",
  contingency_planner: "Draft contingency plan → audit",
  audit: "Compliance verdict → loop back or report",
  report: "Executive HTML report → leadership",
};

fetch("/api/meta").then(r => r.json()).then(m => {
  document.getElementById("mode").textContent =
    m.offline ? "Offline mode (deterministic)" : "Live LLM mode";
});

const $ = id => document.getElementById(id);
$("demand").oninput = e => $("demandv").textContent = e.target.value + "%";
$("wxs").oninput = e => $("wxv").textContent = e.target.value;

function buildFlow() {
  const flow = $("flow");
  flow.innerHTML = "";
  PIPELINE.forEach((n, i) => {
    const el = document.createElement("div");
    el.className = "node"; el.id = "n_" + n; el.textContent = n;
    flow.appendChild(el);
    if (i < PIPELINE.length - 1) {
      const a = document.createElement("span");
      a.className = "arrow"; a.textContent = "→";
      flow.appendChild(a);
    }
  });
}

let _auditCount = 0;
let _prevNode = null;

function onNodeEvent(node, summary) {
  const handoff = $("handoff");
  if (node === "audit") _auditCount++;
  if (_prevNode && _prevNode !== node) {
    const p = $("n_" + _prevNode);
    if (p) { p.classList.remove("active"); p.classList.add("done"); }
  }
  const el = $("n_" + node);
  if (el) {
    // re-entering a node (audit loop) -> brief flash so the motion is visible
    el.classList.remove("done");
    el.classList.remove("active");
    void el.offsetWidth;
    el.classList.add("active");
  }
  let loopTag = "";
  if (_auditCount > 1)
    loopTag = `<span class="loopbadge">audit loop ×${_auditCount}</span>`;
  handoff.innerHTML = `<b>${node}</b> — ${summary || ""}<br>` +
    `<span class="muted">${HANDOFF[node] || ""}</span>${loopTag}`;
  _prevNode = node;
}

function finishFlow() {
  PIPELINE.forEach(n => {
    const x = $("n_" + n);
    if (x) { x.classList.remove("active"); x.classList.add("done"); }
  });
  $("handoff").innerHTML += " &nbsp;✓ complete";
}

function deltaClass(d) { return d > 0 ? "up" : d < 0 ? "down" : "flat"; }

function kpiCards(base, scen, iters, compliant) {
  const bp = base.total_penalty_score || 0, sp = scen.total_penalty_score || 0;
  const d = sp - bp;
  const sign = d > 0 ? "+" : "";
  return `<div class="kpis">
    <div class="kpi"><div class="k">Penalty score</div><div class="v">${sp}</div>
      <div class="d ${deltaClass(d)}">${sign}${d} vs baseline ${bp}</div></div>
    <div class="kpi"><div class="k">Tier-1 units impacted</div><div class="v">${scen.tier1_units_impacted||0}</div>
      <div class="d flat">life-critical at risk</div></div>
    <div class="kpi"><div class="k">Stranded units</div><div class="v">${scen.stranded_units||0}</div>
      <div class="d flat">undeliverable this window</div></div>
    <div class="kpi"><div class="k">Audit iterations</div><div class="v">${iters}</div>
      <div class="d ${compliant?'down':'up'}">${compliant?'compliant':'NON-compliant'}</div></div>
  </div>`;
}

function penaltyBars(bp, sp) {
  const max = Math.max(bp, sp, 1);
  return `<div class="bars">
    <div class="bar-row"><span>Baseline</span>
      <div class="track"><div class="fill base" style="width:${(bp/max*100)||1}%"></div></div>
      <span>${bp}</span></div>
    <div class="bar-row"><span>Scenario</span>
      <div class="track"><div class="fill scen" style="width:${(sp/max*100)||1}%"></div></div>
      <span>${sp}</span></div>
  </div>`;
}

function render(d) {
  const bp = d.baseline_kpis.total_penalty_score || 0;
  const sp = d.scenario_kpis.total_penalty_score || 0;
  $("output").innerHTML = `
    <div class="card">
      <h2>KPI impact — baseline vs scenario</h2>
      ${kpiCards(d.baseline_kpis, d.scenario_kpis, d.audit_iterations, d.audit_compliant)}
      ${penaltyBars(bp, sp)}
    </div>
    <div class="card">
      <h2>Analysis &amp; contingency</h2>
      <div class="grid2">
        <div><div class="muted">Impact analysis</div><div class="prose">${formatStructured(d.impact_analysis)}</div></div>
        <div><div class="muted">Contingency plan (post-audit)</div><div class="prose">${formatStructured(d.contingency_plan)}</div></div>
      </div>
      <div class="muted" style="margin-top:14px">Audit result</div>
      <pre>${escapeHtml(d.audit_result)}</pre>
    </div>
    <div class="card">
      <h2>Executive report
        <button id="exportpdf" class="btn-export">Export to PDF</button>
      </h2>
      <iframe id="reportframe" sandbox srcdoc="${escapeAttr(d.report_html)}"></iframe>
      <div class="muted" style="margin-top:10px">Excluded shipments (data quality)</div>
      <pre>${escapeHtml(d.excluded_md)}</pre>
    </div>`;

  document.getElementById("exportpdf").onclick = () => exportReportPdf(d);
}

// Turn the LLM's "1) Heading: - bullet - bullet 2) ..." text into
// structured HTML (headings + bullet lists) instead of one wall of text.
function formatStructured(raw) {
  let t = (raw || "").trim();
  if (!t) return '<p class="muted">(n/a)</p>';
  t = " " + t;
  t = t.replace(/\s(\d\))\s/g, "\n@@SEC@@$1 ")   // 1)  2)  3) section markers
       .replace(/\s-\s+/g, "\n@@BUL@@");          // " - " bullets
  let html = "", inList = false;
  for (let line of t.split("\n").map(s => s.trim()).filter(Boolean)) {
    if (line.startsWith("@@SEC@@")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += "<h4>" + escapeHtml(line.replace("@@SEC@@", "")) + "</h4>";
    } else if (line.startsWith("@@BUL@@")) {
      if (!inList) { html += "<ul>"; inList = true; }
      let b = escapeHtml(line.replace("@@BUL@@", ""));
      if (/^ESCALATION:/i.test(b)) b = "<b class='esc'>" + b + "</b>";
      html += "<li>" + b + "</li>";
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      html += "<p>" + escapeHtml(line) + "</p>";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function exportReportPdf(d) {
  const sp = d.scenario_kpis.total_penalty_score || 0;
  const bp = d.baseline_kpis.total_penalty_score || 0;
  const w = window.open("", "_blank");
  if (!w) { alert("Pop-up blocked — allow pop-ups to export."); return; }
  w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>SeeWeeS What-if Report</title>
    <style>
      body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
           color:#1c2733;margin:40px;line-height:1.55}
      h1{font-size:20px} h2{font-size:14px;color:#0b7285;margin-top:26px}
      h4{font-size:13px;color:#0b7285;margin:14px 0 5px}
      ul{margin:6px 0;padding-left:20px} li{margin:4px 0}
      .esc{color:#d6453d}
      table{border-collapse:collapse;margin:10px 0;font-size:12px}
      td,th{border:1px solid #d8e0e7;padding:5px 9px;text-align:left}
      .meta{color:#67788a;font-size:12px;margin-bottom:18px}
      pre{white-space:pre-wrap;font-size:12px;background:#f7f9fa;
          border:1px solid #e3e9ef;padding:10px;border-radius:6px}
      @media print{button{display:none}}
    </style></head><body>
    <h1>SeeWeeS — What-if Scenario Report</h1>
    <div class="meta">Generated ${new Date().toLocaleString()} ·
      Baseline penalty ${bp} → Scenario penalty ${sp}
      (Δ ${sp - bp >= 0 ? "+" : ""}${sp - bp}) ·
      Audit iterations ${d.audit_iterations}
      (${d.audit_compliant ? "compliant" : "NON-compliant"})</div>
    <h2>Executive report</h2>
    <div>${d.report_html || "(no report)"}</div>
    <h2>Impact analysis</h2><div>${formatStructured(d.impact_analysis)}</div>
    <h2>Contingency plan (post-audit)</h2><div>${formatStructured(d.contingency_plan)}</div>
    <h2>Audit result</h2><pre>${escapeHtml(d.audit_result)}</pre>
    <h2>Excluded shipments (data quality)</h2><pre>${escapeHtml(d.excluded_md)}</pre>
    </body></html>`);
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 350);
}

function escapeHtml(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function escapeAttr(s){return (s||"").replace(/&/g,"&amp;").replace(/"/g,"&quot;");}

$("run").onclick = () => {
  const btn = $("run");
  btn.disabled = true;
  $("status").textContent = "Agents working — watch the hand-off…";
  buildFlow();
  _auditCount = 0; _prevNode = null;
  $("handoff").textContent = "";
  $("output").innerHTML = '<div class="card empty">Running…</div>';

  const q = new URLSearchParams({
    demand_spike_pct: +$("demand").value,
    closed: $("closure").value || "",
    driver: +$("driver").value,
    truck_standard: +$("std").value,
    truck_temp_controlled: +$("reefer").value,
    weather_corridor: $("wxc").value || "",
    weather_score: +$("wxs").value,
  });
  const es = new EventSource("/api/run/stream?" + q.toString());

  es.addEventListener("node", e => {
    const d = JSON.parse(e.data);
    onNodeEvent(d.node, d.summary);
  });
  es.addEventListener("done", e => {
    es.close();
    finishFlow();
    $("status").textContent = "";
    render(JSON.parse(e.data));
    btn.disabled = false;
  });
  es.onerror = () => {
    es.close();
    $("status").textContent = "Connection error — see server log.";
    btn.disabled = false;
  };
};

buildFlow();
