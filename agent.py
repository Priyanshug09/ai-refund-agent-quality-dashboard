"""
agent.py
--------
The core AI refund agent.

What it does:
  1. Detect intent from user question
  2. Fetch all relevant data from mock backend
  3. Generate an answer (simulated here; swap in OpenAI/Anthropic call if key is available)
  4. Return a full trace dict — same shape as what LangSmith would capture

Design decision: I separated intent detection from answer generation so I can
swap the LLM call without touching the data-fetching logic. The trace dict is
the single source of truth for the evaluator and dashboard.
"""

import time
import os
from datetime import datetime
from mock_data import get_order, get_return_by_order, get_refund_by_order, get_policy

# ── Intent taxonomy ────────────────────────────────────────────────────────────

INTENT_MAP = {
    "refund_status":    ["where is my refund", "refund not received", "refund status",
                         "not received refund", "money back", "refund update",
                         "did my refund", "did i get my refund", "has my refund",
                         "refund go through", "my refund"],
    "partial_refund":   ["partial refund", "why less refund", "deducted", "why partial",
                         "less money", "only half"],
    "cancel_order":     ["cancel order", "cancel my order", "cancellation", "cancel it"],
    "return_status":    ["return picked up", "return status", "return received",
                         "return update", "pickup done"],
    "refund_timeline":  ["how long", "when will i get money", "how many days",
                         "expected date", "timeline", "when will i get",
                         "when will the refund", "when will my refund",
                         "will the refund be credited", "refund be credited",
                         "when will", "how long will"]
}


def detect_intent(question: str) -> str:
    q = question.lower()
    for intent, keywords in INTENT_MAP.items():
        if any(kw in q for kw in keywords):
            return intent
    return "general_refund_query"


# ── Context fetching ───────────────────────────────────────────────────────────

def fetch_context(order_id: str) -> dict:
    """Pull all relevant data for one order. Mirrors what real API calls would return."""
    order  = get_order(order_id)
    ret    = get_return_by_order(order_id)
    refund = get_refund_by_order(order_id)
    policy = get_policy()
    return {"order": order, "return": ret, "refund": refund, "policy": policy}


# ── Answer generation (simulated — no LLM key needed) ─────────────────────────

def _grounded_answer(intent: str, context: dict) -> dict:
    """
    Generates the CORRECT answer using only verified data from context.
    This is what a well-prompted, properly-grounded LLM should produce.
    """
    order  = context["order"]
    ret    = context["return"]
    refund = context["refund"]
    policy = context["policy"]
    oid    = order["order_id"]

    if intent in ("refund_status", "refund_timeline"):
        if refund and ret:
            if refund["refund_status"] == "completed":
                return {
                    "answer": (
                        f"I checked Order {oid}. Your return was received on "
                        f"{ret['return_received_date']}, and your full refund of "
                        f"₹{refund['refund_amount']:,} was completed on "
                        f"{refund['refund_completed_date']} to your {refund['payment_method']}."
                    ),
                    "data_used": ["order", "return", "refund"],
                    "answer_type": "grounded"
                }
            elif refund["refund_status"] == "initiated":
                timeline = policy["refund_timelines"].get(refund["payment_method"], "5–7 business days")
                return {
                    "answer": (
                        f"I checked Order {oid}. Your return was received on "
                        f"{ret['return_received_date']}, and your refund of ₹{refund['refund_amount']:,} "
                        f"was initiated on {refund['refund_initiated_date']} to your "
                        f"{refund['payment_method']}. Refunds to {refund['payment_method']} take "
                        f"{timeline}, so you should receive it by {refund['expected_completion_date']}."
                    ),
                    "data_used": ["order", "return", "refund", "policy"],
                    "answer_type": "grounded"
                }
        elif ret and not refund:
            return {
                "answer": (
                    f"Your return for Order {oid} was received on "
                    f"{ret['return_received_date']}. The refund has not been initiated yet — "
                    f"it typically starts within 1–2 business days of receiving the return."
                ),
                "data_used": ["order", "return"],
                "answer_type": "grounded"
            }

    elif intent == "partial_refund":
        if refund:
            if refund["refund_type"] == "partial":
                return {
                    "answer": (
                        f"For Order {oid}, a partial refund of ₹{refund['refund_amount']:,} was issued "
                        f"instead of the full ₹{order['order_amount']:,}. "
                        f"Reason: {refund.get('partial_refund_reason', 'Item condition affected refund amount.')}"
                    ),
                    "data_used": ["order", "refund"],
                    "answer_type": "grounded"
                }
            else:
                return {
                    "answer": (
                        f"Your refund for Order {oid} is a full refund of ₹{refund['refund_amount']:,}. "
                        "No deductions were made."
                    ),
                    "data_used": ["order", "refund"],
                    "answer_type": "grounded"
                }

    elif intent == "cancel_order":
        cancel = policy["cancellation_policy"]
        if order["order_status"] == "shipped":
            return {
                "answer": (
                    f"Order {oid} has already been shipped. {cancel['after_shipping']} "
                    f"Once delivered, you can initiate a return within the "
                    f"{policy['standard_return_window']}."
                ),
                "data_used": ["order", "policy"],
                "answer_type": "grounded"
            }
        elif order["order_status"] == "delivered":
            return {
                "answer": (
                    f"Order {oid} has already been delivered. You can initiate a return within "
                    f"{policy['standard_return_window']}."
                ),
                "data_used": ["order", "policy"],
                "answer_type": "grounded"
            }

    elif intent == "return_status":
        if ret:
            if ret["return_status"] == "pickup_scheduled":
                return {
                    "answer": (
                        f"Your return for Order {oid} is scheduled for pickup on "
                        f"{ret['return_pickup_date']}. Once received, refund will be initiated "
                        f"within 1–2 business days."
                    ),
                    "data_used": ["order", "return"],
                    "answer_type": "grounded"
                }
            elif ret["return_status"] == "return_received":
                return {
                    "answer": (
                        f"Your return for Order {oid} was received on {ret['return_received_date']}. "
                        "Refund processing has been triggered."
                    ),
                    "data_used": ["order", "return"],
                    "answer_type": "grounded"
                }

    # Fallback: uncertain — data exists but intent unclear
    return {
        "answer": (
            "I can see activity on your account but need more details. "
            "Could you share your order ID so I can give you an exact update?"
        ),
        "data_used": [],
        "answer_type": "uncertain"
    }


# ── Pre-built failure examples for the sample dataset ─────────────────────────

FAILURE_ANSWERS = {
    "hallucinated": [
        "Your refund has already been completed. Please check your bank account.",
        "Your order has been successfully cancelled. Refund will arrive in 2 hours.",
        "We have escalated your case and the refund team will call you shortly.",
        "Your refund of ₹5,000 has been processed to your Credit Card."
    ],
    "incomplete": [
        "Your refund has been initiated.",
        "The return has been received.",
        "Please wait for the refund to be processed.",
        "Your request is under review."
    ],
    "uncertain": [
        "I cannot find the complete details. Please try again later.",
        "I'm not sure about the exact status. Please contact customer support.",
        "The system shows some activity on your account.",
        "Your refund may or may not have been processed."
    ]
}


# ── Main agent entry point ─────────────────────────────────────────────────────

def run_agent(question: str, order_id: str = "ORD-4582",
              inject_failure: str = None, failure_index: int = 0) -> dict:
    """
    Run the agent for one user query.

    Parameters
    ----------
    question      : The user's refund question
    order_id      : Which order to look up
    inject_failure: If set, injects a bad answer type ('hallucinated', 'incomplete', 'uncertain')
                    Used to populate the demo dataset with varied failure cases
    failure_index : Which pre-written failure answer to use

    Returns
    -------
    A trace dict — this is what LangSmith would capture as a run
    """
    start = time.time()

    # Step 1 — Intent
    intent = detect_intent(question)

    # Step 2 — Fetch data
    context = fetch_context(order_id)
    order_found  = context["order"] is not None
    return_found = context["return"] is not None
    refund_found = context["refund"] is not None

    # Step 3 — Generate answer
    if inject_failure and inject_failure in FAILURE_ANSWERS:
        answers = FAILURE_ANSWERS[inject_failure]
        idx = failure_index % len(answers)
        answer_data = {
            "answer": answers[idx],
            "data_used": [],
            "answer_type": inject_failure
        }
    elif context["order"] is None:
        answer_data = {
            "answer": "I couldn't find any order matching your account. Please check your order ID.",
            "data_used": [],
            "answer_type": "uncertain"
        }
    else:
        answer_data = _grounded_answer(intent, context)

    latency_ms = round((time.time() - start) * 1000, 2)
    word_count = len(question.split()) + len(answer_data["answer"].split())

    return {
        "timestamp": datetime.now().isoformat(),
        "user_query": question,
        "order_id": order_id,
        "intent": intent,
        "context_fetched": {
            "order_found":   order_found,
            "return_found":  return_found,
            "refund_found":  refund_found,
            "policy_loaded": True
        },
        "data_used":    answer_data["data_used"],
        "ai_answer":    answer_data["answer"],
        "answer_type":  answer_data["answer_type"],
        "latency_ms":   latency_ms,
        "est_tokens":   word_count,
        "est_cost_usd": round(word_count * 0.000002, 6)
    }
