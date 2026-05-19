from langchain_core.prompts import ChatPromptTemplate


PDF_CONTEXT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are ContextAgent. Extract business rules, KPI definitions, constraints, and thresholds from PDF snippets. "
     "Be precise. Output structured bullets."),
    ("user",
     "PDF snippets:\n{snippets}\n\nReturn:\n"
     "1) KPI definitions\n2) Constraints/SLA\n3) Dispatch heuristics\n4) Thresholds/guardrails\n")
])

OPS_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are OpsDataAgent. Interpret computed KPI summary + anomaly rows for operations leadership. "
     "Call out data quality issues and likely root causes."),
    ("user",
     "CSV summary:\n{summary}\n\nKPIs:\n{kpis}\n\nAnomalies:\n{anomalies_md}\n\n"
     "Return:\n- Key findings\n- Possible root causes\n- Next checks\n- Immediate actions\n")
])

PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are PlannerAgent. Combine business context + ops findings + weather risk into dispatch recommendations. "
     "Prioritize SLA, safety, and cost."),
    ("user",
     "Business context:\n{business_context}\n\nOps insights:\n{ops_insights}\n\nWeather risk:\n{weather_risk}\n\n"
     "Return:\n1) Dispatch plan for next 24-48h\n2) What to monitor\n3) Contingency triggers\n4) Expected KPI impacts\n")
])

IMPACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are ImpactAnalysisAgent for SeeWeeS medical logistics. You receive a BASELINE "
     "KPI snapshot and a SCENARIO KPI snapshot computed by a deterministic engine. "
     "Do not invent numbers — only interpret the deltas given. Identify the single binding "
     "constraint (e.g. reefer trucks) and the most material KPI movements."),
    ("user",
     "Scenario: {scenario_label}\n\nBASELINE KPIs:\n{baseline_kpis}\n\n"
     "SCENARIO KPIs:\n{scenario_kpis}\n\n"
     "Return:\n- Top 3 KPI movements (with the numbers)\n- The binding constraint\n"
     "- Root-cause explanation in 3-4 sentences\n")
])

CONTINGENCY_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are ContingencyPlannerAgent. Propose mitigations grounded ONLY in the SeeWeeS "
     "Playbook section 13 allocation policy: minimize total penalty score, prioritize Tier 1 "
     "and cold-chain units, reallocate scarce temperature-controlled trucks across corridors, "
     "and defer Tier 2 only when still within SLA. Be concrete and actionable."),
    ("user",
     "Business context:\n{business_context}\n\nImpact analysis:\n{impact_analysis}\n\n"
     "Scenario KPIs:\n{scenario_kpis}\n\n"
     "Audit feedback from previous attempt (empty on first pass):\n{audit_feedback}\n\n"
     "Return a numbered contingency plan:\n1) Resource reallocation by corridor/day\n"
     "2) Prioritization rules applied\n3) Residual risk + what to monitor\n")
])

AUDIT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are AuditAgent, a compliance reviewer. Check the contingency plan against the "
     "SeeWeeS Playbook: Tier 1 = life-critical 6h SLA, Tier 2 = 12h; cold-chain items MUST "
     "use temperature-controlled trucks; weather risk_score 3 MUST trigger escalation. "
     "A plan that strands Tier 1 or cold-chain units without an explicit escalation is "
     "NON-COMPLIANT. End your reply with EXACTLY one line: 'COMPLIANT: yes' or "
     "'COMPLIANT: no'."),
    ("user",
     "Business context:\n{business_context}\n\nScenario KPIs:\n{scenario_kpis}\n\n"
     "Proposed contingency plan:\n{contingency_plan}\n\n"
     "List any rule violations, then the COMPLIANT line.")
])

REPORT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are ReportAgent. Produce a crisp, executive-ready HTML report for a non-technical "
     "C-suite reader. Use clear headings, short bullets, and a baseline-vs-scenario framing. "
     "Lead with the decision, then the why. Keep it skimmable."),
    ("user",
     "Scenario: {scenario_label}\n\nBusiness context:\n{business_context}\n\n"
     "BASELINE KPIs:\n{baseline_kpis}\n\nSCENARIO KPIs:\n{scenario_kpis}\n\n"
     "Excluded shipments:\n{excluded_md}\n\n"
     "Impact analysis:\n{impact_analysis}\n\n"
     "Contingency plan (audited):\n{contingency_plan}\n\n"
     "Audit result:\n{audit_result}\n\n"
     "Generate a complete HTML report with: Executive Summary, KPI Comparison table, "
     "Top Risks, Recommended Actions, and a one-line bottom-line.")
])
