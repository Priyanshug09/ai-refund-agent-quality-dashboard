# AI Refund Agent Quality Dashboard

**Builder loop:** Learn → Build → Break → Fix → Business Impact → Push

---

## What I built and why

Most AI customer support demos stop at "look, the chatbot answered the question."
I wanted to go one level deeper: **what happens after the chatbot answers?**
How do you know if it was right? How do you measure it? What do you fix if it isn't?

This project builds a mini AI refund agent for an e-commerce context, then wraps it
in an evaluation dashboard — traces, labels, metrics, and product fix recommendations.

The goal isn't a perfect chatbot. The goal is to demonstrate the full PM loop:
**ship → measure → find failures → recommend fixes.**

---

## The problem I set up

An e-commerce customer asks a refund question. The AI agent has access to:
- Order data
- Return status
- Refund status
- Payment method
- Refund policy

The agent should give a precise, grounded answer.
But it doesn't always. And without evaluation, nobody catches that.

### Five user scenarios I tested

| Scenario | Question | What makes it hard |
|---|---|---|
| 1 | "Where is my refund?" | Refund initiated, not completed. Easy to hallucinate. |
| 2 | "Why did I get a partial refund?" | Requires knowing item condition affected amount. |
| 3 | "Can I cancel after shipping?" | Policy-based. Agent must not invent what it can't do. |
| 4 | "My return was picked up but refund not received" | Multi-step status chain. |
| 5 | "When will I get money back?" | Timeline depends on payment method. |

---

## What the agent does

```
User question
    ↓
Intent detection (keyword-based)
    ↓
Mock API calls (order / return / refund / policy)
    ↓
Answer generation (simulated; plug in OpenAI if key available)
    ↓
Trace dict → Evaluator → Label + Reason + Fix
    ↓
Dashboard
```

---

## The four failure labels

I decided on four labels after thinking about what kinds of failures actually matter to the business:

| Label | What it means | Business impact |
|---|---|---|
| **Grounded** | Answer matches mock data | Safe to send |
| **Hallucinated** | Answer contradicts data | Customer acts on wrong info. High risk. |
| **Incomplete** | Answer exists but missing key fields | Customer calls support again. Medium cost. |
| **Uncertain** | Answer vague when data was available | Wasted interaction. Low-medium cost. |

### Example: the hallucination I caught

**User:** "Where is my refund?"

**Bad AI answer:** "Your refund has already been completed. Please check your bank account."

**Mock data says:** `refund_status: initiated` — not completed.

**Why this matters:** The customer stops chasing. They wait. The refund doesn't arrive. They escalate. Every escalation costs ~$8 in support spend.

---

## Metrics

```
Hallucination Rate = Hallucinated / Total × 100
Grounded Rate      = Grounded / Total × 100
Incomplete Rate    = Incomplete / Total × 100
Uncertain Rate     = Uncertain / Total × 100

Quality Score = Grounded Rate
              - Hallucination Rate × 1.5   ← Heavy penalty: causes direct harm
              - Incomplete Rate    × 0.5
              - Uncertain Rate     × 0.25
```

My sample dataset scores **3.4 / 100**. That number is the point.
You don't know your agent is broken until you measure it.

---

## Product fix logic

| Label | Fix |
|---|---|
| Hallucinated | Add data-validation gate. Block answer generation unless required API fields are present and verified. |
| Incomplete | Update prompt to always include: refund amount, initiation date, payment method, expected timeline. |
| Uncertain | Add clarifying-question flow when order ID missing. If data available but answer vague, escalate to human. |
| Grounded | No fix needed. |

---

## Project structure

```
ai-refund-agent-quality-dashboard/
├── app.py                   # Streamlit dashboard (the main deliverable)
├── agent.py                 # Intent detection + answer generation
├── mock_data.py             # Simulated backend APIs
├── evaluator.py             # Labels each AI answer
├── metrics.py               # Calculates quality metrics + quality score
├── generate_sample_data.py  # Generates sample_outputs.csv
├── sample_outputs.csv       # Pre-populated evaluation dataset
├── requirements.txt
├── .env.example
├── .streamlit/config.toml   # Dark theme config
└── case_study.md
```

---

## How to run

```bash
# 1. Install
pip install -r requirements.txt

# 2. Generate the evaluation dataset
python generate_sample_data.py

# 3. Launch dashboard
streamlit run app.py
```

No API keys needed. Everything runs on simulated data.

---

## LangSmith integration (optional)

If you have a LangSmith key, add it to `.env`:
```
LANGCHAIN_API_KEY=your_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=refund-agent-eval
```

Then wrap `run_agent()` in `agent.py` with `@traceable`.
Each conversation will appear in your LangSmith dashboard with latency, tokens, and eval scores.

---

## What I learned building this

1. **Evaluation logic is harder than the agent itself.** Writing the evaluator — deciding when something is "hallucinated" vs "incomplete" — forced me to define exactly what "correct" means for each intent. That's a product decision, not a technical one.

2. **The quality score formula encodes business priorities.** I chose to penalise hallucinations 1.5× because they cause customers to stop following up. Incomplete answers are annoying but recoverable. That tradeoff is a PM call.

3. **Mock data design matters.** I set `refund_status: "initiated"` on the main test order specifically to trigger hallucination detection. The data architecture shapes the test coverage.

4. **Without a trace, you can't debug.** The Trace Explorer tab shows exactly which API calls were made and which data fields were present when the answer was generated. That's what makes root-cause analysis possible.

---

*Built as part of a 90-day AI PM transition portfolio. Each project follows the builder loop: concept → build → break → fix → business impact → GitHub → case study.*
