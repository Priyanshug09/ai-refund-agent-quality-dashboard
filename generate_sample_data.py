"""
generate_sample_data.py
-----------------------
Generates sample_outputs.csv — the pre-populated evaluation dataset.
Run this once before launching the dashboard: python generate_sample_data.py

The dataset is designed to tell a realistic story:
  8 Grounded (53%) | 3 Hallucinated (20%) | 2 Incomplete (13%) | 2 Uncertain (13%)

This gives a Quality Score ≈ 30-35, which is "needs improvement" —
exactly the kind of signal a PM dashboard should surface.
"""

import csv
import random
import time
from datetime import datetime, timedelta
from agent import run_agent
from evaluator import evaluate

# ── Define the 15 test cases ───────────────────────────────────────────────────
# Each tuple: (question, order_id, inject_failure, failure_index)
# inject_failure=None means let the agent generate a correct answer

TEST_CASES = [
    # Grounded cases — agent does the right thing
    ("Where is my refund?",                          "ORD-4582", None,           0),
    ("My return was picked up but refund not received", "ORD-4582", None,        0),
    ("Why did I get a partial refund?",              "ORD-5119", None,           0),
    ("Can I cancel my order after it was shipped?",  "ORD-6670", None,           0),
    ("What is the status of my return?",             "ORD-3891", None,           0),
    ("When will I get my refund?",                   "ORD-2244", None,           0),
    ("Did my refund go through?",                    "ORD-2244", None,           0),
    ("When will the refund be credited?",            "ORD-5119", None,           0),

    # Hallucinated cases — agent makes stuff up
    ("Where is my refund?",                          "ORD-4582", "hallucinated", 0),
    ("Can I cancel my order?",                       "ORD-6670", "hallucinated", 1),
    ("When will I get money back?",                  "ORD-4582", "hallucinated", 3),

    # Incomplete cases — real data available, answer too brief
    ("When will I get my money back?",               "ORD-4582", "incomplete",   0),
    ("What is my refund status?",                    "ORD-5119", "incomplete",   2),

    # Uncertain cases — agent goes vague when it shouldn't
    ("When will my refund come?",                    "ORD-3891", "uncertain",    0),
    ("How long will the refund take?",               "ORD-4582", "uncertain",    1),
]

# Expected correct answers (for the "expected_answer" column)
EXPECTED_ANSWERS = {
    "ORD-4582_refund_status": (
        "Return received 2026-06-05. Refund of ₹2,499 initiated 2026-06-07 via UPI. "
        "Expected by 2026-06-14 (5–7 business days)."
    ),
    "ORD-5119_partial_refund": (
        "Partial refund of ₹1,249 issued (50% of ₹2,499) because item was returned "
        "in damaged condition. Initiated 2026-06-08, expected by 2026-06-15."
    ),
    "ORD-6670_cancel": (
        "Order ORD-6670 has already shipped. Cannot cancel. Wait for delivery, "
        "then initiate a return within 10 days of delivery."
    ),
    "ORD-3891_return_status": (
        "Return pickup scheduled for 2026-06-10. Once received, refund will be initiated "
        "within 1–2 business days. Credit Card refunds take 7–10 business days."
    ),
    "ORD-2244_refund_status": (
        "Refund of ₹8,999 completed on 2026-05-26 to your Debit Card."
    ),
}


def get_expected(order_id, question):
    """Map question + order to a canned expected answer."""
    q = question.lower()
    if order_id == "ORD-4582":
        return EXPECTED_ANSWERS["ORD-4582_refund_status"]
    if order_id == "ORD-5119" and "partial" in q:
        return EXPECTED_ANSWERS["ORD-5119_partial_refund"]
    if order_id == "ORD-5119":
        return EXPECTED_ANSWERS["ORD-5119_partial_refund"]
    if order_id == "ORD-6670":
        return EXPECTED_ANSWERS["ORD-6670_cancel"]
    if order_id == "ORD-3891":
        return EXPECTED_ANSWERS["ORD-3891_return_status"]
    if order_id == "ORD-2244":
        return EXPECTED_ANSWERS["ORD-2244_refund_status"]
    return "See mock data for ground truth."


def generate():
    rows = []

    for question, order_id, inject, fail_idx in TEST_CASES:
        # Add slight latency variation to make the dashboard realistic
        latency_base = random.uniform(120, 480)

        trace = run_agent(
            question=question,
            order_id=order_id,
            inject_failure=inject,
            failure_index=fail_idx
        )
        trace["latency_ms"] = round(latency_base, 2)

        result = evaluate(trace["ai_answer"], trace)

        rows.append({
            "timestamp":        trace["timestamp"],
            "order_id":         order_id,
            "user_query":       question,
            "intent":           trace["intent"],
            "expected_answer":  get_expected(order_id, question),
            "ai_answer":        trace["ai_answer"],
            "label":            result["label"],
            "failure_reason":   result["reason"],
            "recommended_fix":  result["fix"],
            "latency_ms":       trace["latency_ms"],
            "est_tokens":       trace["est_tokens"],
            "est_cost_usd":     trace["est_cost_usd"],
            "data_used":        ", ".join(trace["data_used"]) if trace["data_used"] else "none"
        })

    fieldnames = list(rows[0].keys())
    with open("sample_outputs.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Print summary
    from collections import Counter
    labels = Counter(r["label"] for r in rows)
    print(f"\n✓ sample_outputs.csv generated — {len(rows)} conversations")
    print(f"  Grounded:     {labels['Grounded']}")
    print(f"  Hallucinated: {labels['Hallucinated']}")
    print(f"  Incomplete:   {labels['Incomplete']}")
    print(f"  Uncertain:    {labels['Uncertain']}")
    print("\n→ Run: streamlit run app.py\n")


if __name__ == "__main__":
    generate()
