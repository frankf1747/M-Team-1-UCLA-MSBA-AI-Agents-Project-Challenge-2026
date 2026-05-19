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

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function animateTrace(trace) {
  buildFlow();
  const handoff = $("handoff");
  const loops = trace.filter(e => e.node === "audit").length;
  for (const ev of trace) {
    const el = $("n_" + ev.node);
    PIPELINE.forEach(n => { const x = $("n_" + n); if (x) x.classList.remove("active"); });
    if (el) {
      el.classList.add("active");
      el.classList.remove("done");
    }
    let loopTag = "";
    if (ev.node === "contingency_planner" && trace.filter(e => e.node === "contingency_planner").length > 1)
      loopTag = `<span class="loopbadge">audit loop ×${loops}</span>`;
    handoff.innerHTML = `<b>${ev.node}</b> — ${ev.summary || ""}<br>` +
      `<span class="muted">${HANDOFF[ev.node] || ""}</span>${loopTag}`;
    await sleep(420);
    if (el) { el.classList.remove("active"); el.classList.add("done"); }
  }
  handoff.innerHTML += ` &nbsp;✓ complete`;
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
        <div><div class="muted">Impact analysis</div><p class="prose">${escapeHtml(d.impact_analysis)}</p></div>
        <div><div class="muted">Contingency plan (post-audit)</div><p class="prose">${escapeHtml(d.contingency_plan)}</p></div>
      </div>
      <div class="muted" style="margin-top:14px">Audit result</div>
      <pre>${escapeHtml(d.audit_result)}</pre>
    </div>
    <div class="card">
      <h2>Executive report</h2>
      <iframe sandbox srcdoc="${escapeAttr(d.report_html)}"></iframe>
      <div class="muted" style="margin-top:10px">Excluded shipments (data quality)</div>
      <pre>${escapeHtml(d.excluded_md)}</pre>
    </div>`;
}

function escapeHtml(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function escapeAttr(s){return (s||"").replace(/&/g,"&amp;").replace(/"/g,"&quot;");}

$("run").onclick = async () => {
  const btn = $("run");
  btn.disabled = true; $("status").textContent = "Running multi-agent pipeline…";
  const closed = $("closure").value ? [$("closure").value] : [];
  const payload = {
    demand_spike_pct: +$("demand").value,
    closed_corridors: closed,
    driver: +$("driver").value,
    truck_standard: +$("std").value,
    truck_temp_controlled: +$("reefer").value,
    weather_corridor: $("wxc").value,
    weather_score: +$("wxs").value,
    label: "Custom scenario",
  };
  try {
    const res = await fetch("/api/run", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    $("status").textContent = "";
    await animateTrace(data.cowork_trace);
    render(data);
  } catch (e) {
    $("status").textContent = "Error: " + e;
  } finally {
    btn.disabled = false;
  }
};

buildFlow();
