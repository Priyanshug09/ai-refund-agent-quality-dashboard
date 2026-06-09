"""
langsmith_integration.py
-------------------------
This is the LangSmith brain of the project.

What this file demonstrates:
  1. @traceable  — every agent step becomes a named span in LangSmith
  2. RunEvaluator — custom evaluator that labels each run Grounded/Hallucinated/Incomplete/Uncertain
  3. Client.create_dataset() — ground-truth examples that evaluators run against
  4. evaluate() — fires the evaluator against the full dataset, produces a scored experiment
  5. Feedback logging — adds structured scores back to each run in LangSmith UI

To use with real LangSmith:
  1. pip install langsmith openai python-dotenv
  2. Set LANGCHAIN_API_KEY in .env
  3. Set LANGCHAIN_TRACING_V2=true
  4. python langsmith_integration.py

What you'll see in LangSmith after running:
  - Project "refund-agent-eval" with all runs
  - Each run shows the full span tree: pipeline → intent → fetch → answer
  - Evaluator scores per run (0.0 = fail, 1.0 = pass)
  - Experiment comparison view
"""

import os
import time
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── LangSmith imports ──────────────────────────────────────────────────────────
from langsmith import Client, traceable
from langsmith.evaluation import evaluate, EvaluationResult, RunEvaluator

# ── Optional: OpenAI for real LLM answers ─────────────────────────────────────
try:
    from openai import OpenAI
    openai_client = OpenAI()
    USE_REAL_LLM = True
except Exception:
    USE_REAL_LLM = False

# ── LangSmith client ───────────────────────────────────────────────────────────
ls_client = Client()

# ── Mock data (same as mock_data.py, inlined so this file is self-contained) ───
ORDERS = {
    "ORD-4582": {"order_id":"ORD-4582","product":"Nike Air Max Running Shoes","order_amount":2499,"order_status":"delivered","payment_method":"UPI"},
    "ORD-3891": {"order_id":"ORD-3891","product":"Sony WH-1000XM5 Headphones","order_amount":18999,"order_status":"delivered","payment_method":"Credit Card"},
    "ORD-2244": {"order_id":"ORD-2244","product":"JBL Flip 6 Bluetooth Speaker","order_amount":8999,"order_status":"delivered","payment_method":"Debit Card"},
    "ORD-5119": {"order_id":"ORD-5119","product":"Wildcraft Laptop Backpack","order_amount":2499,"order_status":"delivered","payment_method":"UPI"},
    "ORD-6670": {"order_id":"ORD-6670","product":"Noise ColorFit Pro Smart Watch","order_amount":3499,"order_status":"shipped","payment_method":"UPI"},
}
RETURNS = {
    "ORD-4582": {"return_status":"return_received","return_received_date":"2026-06-05","return_condition":"good"},
    "ORD-3891": {"return_status":"pickup_scheduled","return_pickup_date":"2026-06-10","return_received_date":None},
    "ORD-2244": {"return_status":"return_received","return_received_date":"2026-05-22","return_condition":"good"},
    "ORD-5119": {"return_status":"return_received","return_received_date":"2026-06-07","return_condition":"damaged"},
}
REFUNDS = {
    "ORD-4582": {"refund_status":"initiated","refund_amount":2499,"refund_initiated_date":"2026-06-07","expected_completion_date":"2026-06-14","refund_type":"full","payment_method":"UPI"},
    "ORD-2244": {"refund_status":"completed","refund_amount":8999,"refund_initiated_date":"2026-05-23","refund_completed_date":"2026-05-26","refund_type":"full","payment_method":"Debit Card"},
    "ORD-5119": {"refund_status":"initiated","refund_amount":1249,"refund_initiated_date":"2026-06-08","expected_completion_date":"2026-06-15","refund_type":"partial","payment_method":"UPI","partial_reason":"Item returned damaged. 50% refund applied per policy."},
}
POLICY = {
    "refund_timelines": {"UPI":"5–7 business days","Credit Card":"7–10 business days","Debit Card":"5–7 business days"},
    "return_window": "10 days from delivery",
    "cancellation": {"shipped": "Cannot cancel. Wait for delivery, then return within 10 days."},
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — TRACED AGENT FUNCTIONS
# Each @traceable call creates a named span in LangSmith with inputs + outputs.
# ═══════════════════════════════════════════════════════════════════════════════

@traceable(
    name="detect-intent",
    run_type="chain",
    tags=["refund-agent", "intent"],
    project_name="refund-agent-eval"
)
def detect_intent(question: str) -> str:
    """
    Span type: chain
    What LangSmith captures: input question → detected intent string
    """
    q = question.lower()
    if any(k in q for k in ["partial", "why less", "why did i get less"]): return "partial_refund"
    if any(k in q for k in ["cancel"]): return "cancel_order"
    if any(k in q for k in ["return status", "return picked", "pickup"]): return "return_status"
    if any(k in q for k in ["how long", "when will", "timeline"]): return "refund_timeline"
    return "refund_status"


@traceable(
    name="fetch-order-context",
    run_type="tool",
    tags=["refund-agent", "data-fetch"],
    project_name="refund-agent-eval"
)
def fetch_context(order_id: str) -> dict:
    """
    Span type: tool  (represents a tool/API call in LangSmith)
    What LangSmith captures: order_id → full context dict with all backend data
    LangSmith shows each dict key as a named field in the span output.
    """
    return {
        "order":  ORDERS.get(order_id),
        "return": RETURNS.get(order_id),
        "refund": REFUNDS.get(order_id),
        "policy": POLICY,
        "order_found":  order_id in ORDERS,
        "return_found": order_id in RETURNS,
        "refund_found": order_id in REFUNDS,
    }


@traceable(
    name="generate-refund-answer",
    run_type="llm",
    tags=["refund-agent", "generation"],
    project_name="refund-agent-eval"
)
def generate_answer(intent: str, context: dict, question: str) -> dict:
    """
    Span type: llm  (LangSmith shows token counts, model name, cost estimate for this)
    Returns: answer string + metadata that LangSmith logs as run output
    """
    order  = context.get("order")
    ret    = context.get("return")
    refund = context.get("refund")
    policy = context.get("policy")

    if not order:
        return {"answer": "I couldn't find any order matching your account.", "tokens": 12, "model": "simulated"}

    oid = order["order_id"]

    if USE_REAL_LLM:
        # Real LLM path — LangSmith captures the actual token count and model name
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a refund support agent. Answer using ONLY the order data provided. "
                    "Always include: refund status, amount, dates, and expected timeline. "
                    "NEVER say 'completed' if refund_status is 'initiated'."
                )},
                {"role": "user", "content": f"Question: {question}\nOrder data: {json.dumps(context, default=str)}"}
            ],
            max_tokens=150
        )
        answer = resp.choices[0].message.content
        tokens = resp.usage.total_tokens
        return {"answer": answer, "tokens": tokens, "model": "gpt-4o-mini"}

    # Simulated path (no LLM key needed) — same logic as agent.py
    if intent in ("refund_status", "refund_timeline") and refund and ret:
        if refund["refund_status"] == "completed":
            answer = (f"I checked Order {oid}. Your refund of ₹{refund['refund_amount']:,} was completed "
                      f"on {refund.get('refund_completed_date')} to your {refund['payment_method']}.")
        elif refund["refund_status"] == "initiated":
            timeline = policy["refund_timelines"].get(refund["payment_method"], "5–7 business days")
            answer = (f"I checked Order {oid}. Your return was received on {ret.get('return_received_date')}, "
                      f"and your refund of ₹{refund['refund_amount']:,} was initiated on "
                      f"{refund['refund_initiated_date']} to your {refund['payment_method']}. "
                      f"Refunds to {refund['payment_method']} take {timeline}, "
                      f"so you should receive it by {refund.get('expected_completion_date')}.")
        else:
            answer = f"Your return for Order {oid} has been received. Refund processing is underway."

    elif intent == "partial_refund" and refund:
        answer = (f"For Order {oid}, a partial refund of ₹{refund['refund_amount']:,} was issued "
                  f"instead of the full ₹{order['order_amount']:,}. "
                  f"Reason: {refund.get('partial_reason', 'Item condition affected refund amount.')}")

    elif intent == "cancel_order":
        if order["order_status"] == "shipped":
            answer = (f"Order {oid} has already shipped. {policy['cancellation']['shipped']} "
                      f"You can initiate a return within {policy['return_window']}.")
        else:
            answer = f"Order {oid} cannot be cancelled at this stage. Please contact support."

    elif intent == "return_status" and ret:
        if ret.get("return_status") == "pickup_scheduled":
            answer = (f"Your return for Order {oid} is scheduled for pickup on "
                      f"{ret.get('return_pickup_date')}. Refund will be initiated within 1–2 business days of receipt.")
        else:
            answer = (f"Your return for Order {oid} was received on {ret.get('return_received_date')}. "
                      "Refund processing has been triggered.")
    else:
        answer = "I need more details to help you. Could you share your order ID?"

    word_count = len(answer.split())
    return {
        "answer": answer,
        "tokens": word_count * 4,  # rough token estimate
        "model": "simulated"
    }


@traceable(
    name="refund-agent-pipeline",
    run_type="chain",
    tags=["refund-agent"],
    project_name="refund-agent-eval"
)
def run_agent_traced(question: str, order_id: str) -> dict:
    """
    TOP-LEVEL SPAN — this is what LangSmith shows as the parent run.

    Child spans that appear inside it in LangSmith:
      ├── detect-intent      (chain)
      ├── fetch-order-context (tool)
      └── generate-refund-answer (llm)

    What LangSmith captures at this level:
      - Total latency (start to end of this function)
      - All child span latencies
      - Final input (question + order_id)
      - Final output (answer + metadata)
    """
    intent  = detect_intent(question)
    context = fetch_context(order_id)
    result  = generate_answer(intent, context, question)

    return {
        "answer":   result["answer"],
        "intent":   intent,
        "order_id": order_id,
        "tokens":   result["tokens"],
        "model":    result["model"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — CUSTOM RUN EVALUATOR
# This is what LangSmith calls after each run to attach a score.
# In the LangSmith UI, you see these scores as "feedback" on each run.
# ═══════════════════════════════════════════════════════════════════════════════

class RefundAnswerEvaluator(RunEvaluator):
    """
    Custom evaluator that LangSmith calls for each run in the dataset.

    What it does:
      - Reads run.outputs["answer"] (what the agent said)
      - Reads run.inputs["order_id"] (to pull ground-truth data)
      - Returns an EvaluationResult with score + label + reason

    In LangSmith UI, these appear as:
      - A "Feedback" column in the run list (score: 0.0 to 1.0)
      - Color-coded bars in the experiment comparison view
      - Filterable tags (Grounded / Hallucinated / Incomplete / Uncertain)
    """

    HALLUCINATION_SIGNALS = [
        "already been completed", "refund completed", "has been processed",
        "check your bank account", "successfully cancelled",
        "will arrive in 2 hours", "call you shortly"
    ]
    UNCERTAINTY_SIGNALS = [
        "i'm not sure", "cannot find", "try again later",
        "contact customer support", "may or may not"
    ]

    def evaluate_run(self, run, example=None) -> EvaluationResult:
        """Called by LangSmith's evaluate() for each run."""
        ai_answer = (run.outputs or {}).get("answer", "")
        order_id  = (run.inputs  or {}).get("order_id", "")

        label, score, reason, fix = self._classify(ai_answer, order_id)

        # LangSmith stores: key (metric name), score (0-1), value (label), comment (reason)
        return EvaluationResult(
            key="answer_correctness",
            score=score,
            value=label,
            comment=f"{reason} | Fix: {fix}"
        )

    def _classify(self, answer: str, order_id: str):
        lower   = answer.lower()
        order   = ORDERS.get(order_id)
        refund  = REFUNDS.get(order_id)
        ret     = RETURNS.get(order_id)

        # ── Hallucination ──────────────────────────────────────────────────────
        if refund and refund["refund_status"] == "initiated":
            if any(s in lower for s in self.HALLUCINATION_SIGNALS):
                return ("Hallucinated", 0.0,
                        f"AI implied refund was complete. refund_status = 'initiated'.",
                        "Add pre-generation gate: check refund_status before using 'completed' language.")

        if order and order["order_status"] == "shipped":
            if "successfully cancelled" in lower or "cancellation has been processed" in lower:
                return ("Hallucinated", 0.0,
                        "AI claimed cancellation done. order_status = 'shipped'.",
                        "Block cancellation confirmation on shipped orders.")

        # ── Uncertain ─────────────────────────────────────────────────────────
        if any(s in lower for s in self.UNCERTAINTY_SIGNALS):
            if order and (ret or refund):
                return ("Uncertain", 0.25,
                        "Vague answer despite data being available.",
                        "Narrow fallback triggers. Force grounded path when order data exists.")

        # ── Incomplete ────────────────────────────────────────────────────────
        if refund and ret and order:
            missing = []
            if str(refund["refund_amount"]) not in answer.replace(",", ""):
                missing.append("refund_amount")
            if (refund["refund_status"] != "completed"
                    and refund.get("expected_completion_date")
                    and refund["expected_completion_date"] not in answer):
                missing.append("expected_completion_date")
            if len(answer.split()) < 18 and missing:
                return ("Incomplete", 0.5,
                        f"Answer too brief. Missing fields: {', '.join(missing)}.",
                        "Update prompt: mandate amount + date + timeline in every response.")

        # ── Grounded ──────────────────────────────────────────────────────────
        return ("Grounded", 1.0,
                "Answer supported by backend data. Key facts verified.",
                "No fix needed.")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — DATASET CREATION
# LangSmith datasets are ground-truth examples used as evaluation inputs.
# Each example has: inputs (what to send the agent) + outputs (expected answer).
# ═══════════════════════════════════════════════════════════════════════════════

EVAL_EXAMPLES = [
    {
        "inputs":  {"question": "Where is my refund?", "order_id": "ORD-4582"},
        "outputs": {"answer": "Return received 2026-06-05. Refund of ₹2,499 initiated 2026-06-07 via UPI. Expected by 2026-06-14 (5–7 business days)."}
    },
    {
        "inputs":  {"question": "Why did I get a partial refund?", "order_id": "ORD-5119"},
        "outputs": {"answer": "Partial refund of ₹1,249 (50% of ₹2,499) because item was returned damaged. Initiated 2026-06-08, expected 2026-06-15."}
    },
    {
        "inputs":  {"question": "Can I cancel my order after shipping?", "order_id": "ORD-6670"},
        "outputs": {"answer": "Cannot cancel ORD-6670 (already shipped). Wait for delivery then return within 10 days."}
    },
    {
        "inputs":  {"question": "Did my refund go through?", "order_id": "ORD-2244"},
        "outputs": {"answer": "Your full refund of ₹8,999 was completed on 2026-05-26 to your Debit Card."}
    },
    {
        "inputs":  {"question": "What is my return status?", "order_id": "ORD-3891"},
        "outputs": {"answer": "Return pickup scheduled for 2026-06-10. After receipt, refund initiated within 1–2 days. Credit Card: 7–10 business days."}
    },
]


def create_dataset(dataset_name: str = "refund-agent-eval-v1") -> object:
    """
    Creates a LangSmith dataset with ground-truth examples.
    These examples are what the evaluator runs against.

    In LangSmith UI: Datasets → refund-agent-eval-v1 → Examples tab
    """
    # Check if dataset already exists
    existing = list(ls_client.list_datasets(dataset_name=dataset_name))
    if existing:
        print(f"Dataset '{dataset_name}' already exists. Using existing.")
        return existing[0]

    dataset = ls_client.create_dataset(
        dataset_name=dataset_name,
        description="Ground-truth evaluation dataset for the AI refund agent. 5 scenarios covering all major refund query types."
    )

    ls_client.create_examples(
        inputs  = [e["inputs"]  for e in EVAL_EXAMPLES],
        outputs = [e["outputs"] for e in EVAL_EXAMPLES],
        dataset_id=dataset.id
    )

    print(f"Created dataset '{dataset_name}' with {len(EVAL_EXAMPLES)} examples.")
    return dataset


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — RUN EVALUATION
# evaluate() fires run_agent_traced on every dataset example,
# then runs RefundAnswerEvaluator on each output.
# Results appear as a named Experiment in LangSmith.
# ═══════════════════════════════════════════════════════════════════════════════

def run_evaluation(dataset_name: str = "refund-agent-eval-v1"):
    """
    What LangSmith does when this runs:
      1. Fetches all examples from the dataset
      2. Calls run_agent_traced(question, order_id) for each example
      3. Logs each call as a traced run (with full span tree)
      4. Calls RefundAnswerEvaluator.evaluate_run() on each output
      5. Attaches scores to each run as "feedback"
      6. Aggregates scores into an Experiment with avg score, pass rate, etc.

    In LangSmith UI: Projects → refund-agent-eval → Experiments → refund-eval-v1
    """
    results = evaluate(
        run_agent_traced,               # the function to evaluate
        data=dataset_name,             # LangSmith dataset name
        evaluators=[RefundAnswerEvaluator()],  # our custom evaluator
        experiment_prefix="refund-eval",       # shows as "refund-eval-20260610-..."
        metadata={
            "version": "1.0",
            "description": "Initial evaluation run",
            "model": "simulated" if not USE_REAL_LLM else "gpt-4o-mini"
        }
    )
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — MANUAL FEEDBACK LOGGING
# You can also add feedback to individual runs programmatically.
# Useful for human review scores or downstream metric logging.
# ═══════════════════════════════════════════════════════════════════════════════

def log_feedback(run_id: str, score: float, label: str, reason: str):
    """
    Attaches a feedback score to an existing run.
    In LangSmith UI: Run detail → Feedback tab → shows score + comment.
    """
    ls_client.create_feedback(
        run_id=run_id,
        key="human_review",
        score=score,
        value=label,
        comment=reason
    )
    print(f"Logged feedback for run {run_id}: {label} (score={score})")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — run everything end-to-end
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("── Step 1: Create dataset ────────────────────────────────")
    dataset = create_dataset()

    print("\n── Step 2: Run single traced query ───────────────────────")
    result = run_agent_traced(
        question="Where is my refund?",
        order_id="ORD-4582"
    )
    print(f"Answer: {result['answer'][:80]}...")
    print("→ Check LangSmith project 'refund-agent-eval' to see the full trace.")

    print("\n── Step 3: Run full evaluation ───────────────────────────")
    print("Running evaluator against all 5 dataset examples...")
    eval_results = run_evaluation()
    print(f"Evaluation complete. Check LangSmith Experiments for scores.")
    print("→ Look for experiment 'refund-eval-...' in project 'refund-agent-eval'")

    print("\n✓ Done. Open LangSmith to see:")
    print("  - Full trace trees for each run")
    print("  - answer_correctness scores per example")
    print("  - Experiment aggregate: avg score, pass/fail rate")
