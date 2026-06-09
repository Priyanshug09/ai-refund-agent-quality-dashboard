"""
metrics.py
----------
Calculates the quality metrics shown on the dashboard.

Formula notes:
  - Hallucination Rate = hallucinated / total × 100
  - Grounded Rate      = grounded / total × 100
  - Quality Score      = grounded_rate - (hallucination_rate × 1.5) - (incomplete_rate × 0.5) - (uncertain_rate × 0.25)
    Rationale: Hallucinations are penalised 1.5× because they cause direct customer harm
    (wrong actions, false expectations). Incomplete answers are annoying but not dangerous.
"""

import pandas as pd
from typing import Dict, List


def calculate_metrics(df: pd.DataFrame) -> Dict:
    total = len(df)
    if total == 0:
        return {}

    counts = df["label"].value_counts().to_dict()
    grounded    = counts.get("Grounded",    0)
    hallucinated = counts.get("Hallucinated", 0)
    incomplete  = counts.get("Incomplete",  0)
    uncertain   = counts.get("Uncertain",   0)

    g_rate = round((grounded    / total) * 100, 1)
    h_rate = round((hallucinated / total) * 100, 1)
    i_rate = round((incomplete  / total) * 100, 1)
    u_rate = round((uncertain   / total) * 100, 1)

    return {
        "total":             total,
        "grounded_count":    grounded,
        "hallucinated_count": hallucinated,
        "incomplete_count":  incomplete,
        "uncertain_count":   uncertain,
        "grounded_rate":     g_rate,
        "hallucination_rate": h_rate,
        "incomplete_rate":   i_rate,
        "uncertain_rate":    u_rate,
        "avg_latency_ms":    round(df["latency_ms"].mean(), 1) if "latency_ms" in df.columns else None,
        "avg_cost_usd":      round(df["est_cost_usd"].mean(), 6) if "est_cost_usd" in df.columns else None,
        "total_cost_usd":    round(df["est_cost_usd"].sum(), 5) if "est_cost_usd" in df.columns else None,
    }


def quality_score(metrics: Dict) -> float:
    if not metrics:
        return 0.0
    raw = (
        metrics["grounded_rate"]
        - metrics["hallucination_rate"] * 1.5
        - metrics["incomplete_rate"]    * 0.5
        - metrics["uncertain_rate"]     * 0.25
    )
    return round(max(0.0, min(100.0, raw)), 1)


def insights(metrics: Dict) -> List[str]:
    tips = []
    if metrics.get("hallucination_rate", 0) > 15:
        tips.append(f"🚨 Hallucination rate is {metrics['hallucination_rate']}%. Add a data-validation gate before answer generation.")
    if metrics.get("incomplete_rate", 0) > 20:
        tips.append(f"📋 Incomplete rate is {metrics['incomplete_rate']}%. Update prompt to always include amount, date, and timeline.")
    if metrics.get("uncertain_rate", 0) > 10:
        tips.append(f"❓ Uncertain rate is {metrics['uncertain_rate']}%. Add clarifying question flow or escalate to human support.")
    if metrics.get("grounded_rate", 0) >= 60:
        tips.append(f"✅ Grounded rate is {metrics['grounded_rate']}%. Core data-fetching pipeline is working.")
    avg = metrics.get("avg_latency_ms", 0) or 0
    if avg > 3000:
        tips.append(f"⏱️ Avg latency {avg}ms is high. Consider pre-fetching common order data.")
    return tips or ["All metrics within acceptable range."]
