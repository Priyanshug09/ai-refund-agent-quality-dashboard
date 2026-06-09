"""
evaluator.py
------------
Labels each AI answer. The four labels mirror what a human QA reviewer would assign.

My labeling logic:
  1. Check for hallucination first — it's the most dangerous failure
  2. Then check for uncertainty
  3. Then check for incompleteness
  4. If none of the above, it's Grounded

Why this order? A hallucinated-but-complete answer is worse than an
incomplete-but-honest one. The priority order encodes that risk ranking.
"""

import re
from mock_data import get_order, get_return_by_order, get_refund_by_order

LABELS = ["Grounded", "Hallucinated", "Incomplete", "Uncertain"]

PRODUCT_FIXES = {
    "Grounded":     "No fix needed. Answer is correct and grounded in data.",
    "Hallucinated": "Add a data validation gate: block final answer generation unless required API fields are present and verified.",
    "Incomplete":   "Update prompt to always include: refund amount, initiation date, payment method, and expected timeline when available.",
    "Uncertain":    "Add a clarifying-question flow when order ID is missing. If data is available but answer is vague, route to human support."
}

HALLUCINATION_SIGNALS = [
    "already been completed",
    "refund completed",
    "has been processed",
    "check your bank account",
    "successfully cancelled",
    "refund will arrive in",
    "call you shortly",
    "has been done"
]

UNCERTAINTY_SIGNALS = [
    "i'm not sure",
    "cannot find",
    "try again later",
    "may or may not",
    "some activity",
    "unclear",
    "contact customer support",
    "contact support for more"
]


def evaluate(ai_answer: str, trace: dict) -> dict:
    """
    Evaluate one AI answer against the ground-truth mock data.

    Returns a dict with: label, reason, fix, confidence
    """
    order_id = trace.get("order_id", "")
    order  = get_order(order_id)
    ret    = get_return_by_order(order_id)
    refund = get_refund_by_order(order_id)

    answer_lower = ai_answer.lower()

    # ── 1. Hallucination check ─────────────────────────────────────────────────
    # Signal A: answer claims refund is complete when data says initiated
    if refund and refund["refund_status"] == "initiated":
        if any(sig in answer_lower for sig in HALLUCINATION_SIGNALS):
            return {
                "label": "Hallucinated",
                "reason": (
                    f"AI implied the refund was completed or processed, "
                    f"but mock data shows refund_status = '{refund['refund_status']}'. "
                    f"This is a factual error the customer would act on incorrectly."
                ),
                "fix": PRODUCT_FIXES["Hallucinated"],
                "confidence": "high"
            }

    # Signal B: wrong refund amount mentioned
    if refund and order:
        amounts_in_answer = re.findall(r'₹([\d,]+)', ai_answer)
        for amt_str in amounts_in_answer:
            amt = int(amt_str.replace(",", ""))
            # Flag if the amount doesn't match refund amount OR original order amount
            if amt != refund["refund_amount"] and amt != order["order_amount"] and amt > 100:
                return {
                    "label": "Hallucinated",
                    "reason": (
                        f"AI mentioned ₹{amt_str} which doesn't match "
                        f"refund_amount (₹{refund['refund_amount']:,}) or "
                        f"order_amount (₹{order['order_amount']:,})."
                    ),
                    "fix": PRODUCT_FIXES["Hallucinated"],
                    "confidence": "high"
                }

    # Signal C: claims cancellation was done on a shipped order
    if order and order["order_status"] == "shipped":
        if "successfully cancelled" in answer_lower or "cancellation has been processed" in answer_lower:
            return {
                "label": "Hallucinated",
                "reason": (
                    f"AI claimed the order was cancelled, but order_status = 'shipped'. "
                    "Cancellation is not possible at this stage."
                ),
                "fix": PRODUCT_FIXES["Hallucinated"],
                "confidence": "high"
            }

    # ── 2. Uncertainty check ───────────────────────────────────────────────────
    # Uncertain = answer is vague AND data was actually available to answer correctly
    if any(sig in answer_lower for sig in UNCERTAINTY_SIGNALS):
        data_was_available = order is not None and (ret is not None or refund is not None)
        if data_was_available:
            return {
                "label": "Uncertain",
                "reason": (
                    "Answer is vague even though the order, return, and refund data "
                    "are all present in the system. The AI had enough information to answer."
                ),
                "fix": PRODUCT_FIXES["Uncertain"],
                "confidence": "high"
            }

    # ── 3. Incompleteness check ────────────────────────────────────────────────
    # Incomplete = answer exists but is missing key fields that WERE available
    if refund and ret and order:
        missing = []
        amount_str = str(refund["refund_amount"])
        if amount_str not in ai_answer.replace(",", ""):
            missing.append("refund amount")
        if refund.get("refund_initiated_date") and refund["refund_initiated_date"] not in ai_answer:
            missing.append("initiation date")
        # Only check expected_completion_date if refund is NOT yet completed
        if (refund["refund_status"] != "completed"
                and refund.get("expected_completion_date")
                and refund["expected_completion_date"] not in ai_answer):
            missing.append("expected completion date")

        word_count = len(ai_answer.split())
        if word_count < 18 and len(missing) >= 1:
            return {
                "label": "Incomplete",
                "reason": (
                    f"Answer is too brief ({word_count} words) given available data. "
                    f"Missing: {', '.join(missing)}."
                ),
                "fix": PRODUCT_FIXES["Incomplete"],
                "confidence": "high"
            }

        if len(missing) >= 2:
            return {
                "label": "Incomplete",
                "reason": (
                    f"Answer exists but omits key fields: {', '.join(missing)}. "
                    "Customer can't determine when or how much to expect."
                ),
                "fix": PRODUCT_FIXES["Incomplete"],
                "confidence": "medium"
            }

    # ── 4. Default: Grounded ───────────────────────────────────────────────────
    return {
        "label": "Grounded",
        "reason": "Answer is supported by available data. Key facts match mock data.",
        "fix": PRODUCT_FIXES["Grounded"],
        "confidence": "high"
    }
