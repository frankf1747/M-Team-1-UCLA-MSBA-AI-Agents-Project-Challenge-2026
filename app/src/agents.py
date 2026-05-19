from __future__ import annotations
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from prompts import (
    PDF_CONTEXT_PROMPT, OPS_ANALYSIS_PROMPT, PLANNER_PROMPT, REPORT_PROMPT,
    IMPACT_PROMPT, CONTINGENCY_PROMPT, AUDIT_PROMPT,
)

_llm = None


def _get_llm() -> ChatOpenAI:
    """Lazy singleton so importing this module never requires an API key."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0.2,
            tags=["msba-demo", "multi-agent"],
            metadata={"repo": "MSBA_AI_Agents_Demo"},
        )
    return _llm


class _LazyLLM:
    def invoke(self, *a, **k):
        return _get_llm().invoke(*a, **k)


llm = _LazyLLM()


def run_context_agent(snippets: str) -> str:
    return llm.invoke(PDF_CONTEXT_PROMPT.format_messages(snippets=snippets)).content

def run_ops_agent(summary: Dict[str, Any], kpis: Dict[str, Any], anomalies_md: str) -> str:
    return llm.invoke(OPS_ANALYSIS_PROMPT.format_messages(
        summary=summary, kpis=kpis, anomalies_md=anomalies_md
    )).content

def run_planner_agent(business_context: str, ops_insights: str, weather_risk: Dict[str, Any]) -> str:
    return llm.invoke(PLANNER_PROMPT.format_messages(
        business_context=business_context,
        ops_insights=ops_insights,
        weather_risk=weather_risk
    )).content

def run_impact_agent(scenario_label: str, baseline_kpis: Dict[str, Any],
                     scenario_kpis: Dict[str, Any]) -> str:
    return llm.invoke(IMPACT_PROMPT.format_messages(
        scenario_label=scenario_label,
        baseline_kpis=baseline_kpis,
        scenario_kpis=scenario_kpis,
    )).content


def run_contingency_agent(business_context: str, impact_analysis: str,
                          scenario_kpis: Dict[str, Any],
                          audit_feedback: str = "") -> str:
    return llm.invoke(CONTINGENCY_PROMPT.format_messages(
        business_context=business_context,
        impact_analysis=impact_analysis,
        scenario_kpis=scenario_kpis,
        audit_feedback=audit_feedback or "(none)",
    )).content


def run_audit_agent(business_context: str, contingency_plan: str,
                    scenario_kpis: Dict[str, Any]) -> tuple[str, bool]:
    text = llm.invoke(AUDIT_PROMPT.format_messages(
        business_context=business_context,
        contingency_plan=contingency_plan,
        scenario_kpis=scenario_kpis,
    )).content
    last = text.strip().splitlines()[-1].lower() if text.strip() else ""
    compliant = "compliant: yes" in last
    return text, compliant


def run_report_agent(
    scenario_label: str,
    business_context: str,
    baseline_kpis: Dict[str, Any],
    scenario_kpis: Dict[str, Any],
    excluded_md: str,
    impact_analysis: str,
    contingency_plan: str,
    audit_result: str,
) -> str:
    html = llm.invoke(REPORT_PROMPT.format_messages(
        scenario_label=scenario_label,
        business_context=business_context,
        baseline_kpis=baseline_kpis,
        scenario_kpis=scenario_kpis,
        excluded_md=excluded_md,
        impact_analysis=impact_analysis,
        contingency_plan=contingency_plan,
        audit_result=audit_result,
    )).content
    return _strip_code_fences(html)


def _strip_code_fences(text: str) -> str:
    """LLMs often wrap HTML in ```html ... ``` fences which won't render."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
