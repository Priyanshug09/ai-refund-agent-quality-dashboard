# Case Study: AI Refund Agent Quality Dashboard

**Project:** AI Refund Agent Evaluation System  
**Stack:** Python · Streamlit · LangSmith (optional)  
**Status:** Built, evaluated, documented

---

## 1. Product Context

I was working through the AI PM builder loop on evaluation frameworks. The concept I wanted to build on: **most AI product failures are product decisions that were never made, not model failures.**

Nowhere is that more true than in AI customer support. You deploy an agent. It starts answering refund questions. Customers don't complain about hallucinations — they just stop trusting you. By the time you notice, the damage is done.

I built this project to demonstrate the evaluation layer that prevents that.

The scenario: an e-commerce platform uses an AI agent to handle refund queries. The agent has access to order data, return status, refund status, and policy. The question I wanted to answer: **how do you know if it's actually working?**

---

## 2. User Journey

1. Customer places an order and later requests a return.
2. Return is picked up and received at the warehouse.
3. Refund is initiated but not yet completed.
4. Customer asks: "Where is my refund?"

That last step is where the AI agent enters. And that last step is where things can go wrong in exactly the ways a dashboard like this catches.

---

## 3. AI Touchpoints

The agent handles five distinct query types:

| Intent | Example Query | Risk |
|---|---|---|
| `refund_status` | "Where is my refund?" | Hallucination: claiming completed when initiated |
| `partial_refund` | "Why did I get a partial refund?" | Incomplete: not explaining why |
| `cancel_order` | "Can I cancel after shipping?" | Hallucination: claiming cancellation done |
| `return_status` | "My return was picked up, when is my refund?" | Incomplete: missing timeline |
| `refund_timeline` | "How long will my refund take?" | Uncertain: vague without payment-method-specific data |

---

## 4. Required APIs / Data

I mapped out what data the agent actually needs to give a grounded answer:

| Data Source | Fields Used | What breaks without it |
|---|---|---|
| Orders API | `order_id`, `order_status`, `order_amount`, `payment_method` | Can't confirm order context |
| Returns API | `return_status`, `return_received_date` | Can't confirm return was received |
| Refunds API | `refund_status`, `refund_amount`, `refund_initiated_date`, `expected_completion_date` | Hallucination risk is highest here |
| Policy KB | `refund_timelines` by payment method | Can't give timeline without this |

**Key insight:** The single most dangerous missing field is `refund_status`. If the agent doesn't check this field before answering, it will assume the refund is complete and tell the customer to check their bank account. That's the hallucination that ends trust.

---

## 5. Expected vs Bad AI Answer

### Scenario: Order ORD-4582

**Mock data state:**
- Return received: 2026-06-05
- Refund status: `initiated` (NOT completed)
- Refund amount: ₹2,499
- Payment method: UPI
- Expected completion: 2026-06-14

---

**Expected correct answer:**

> "I checked Order ORD-4582. Your return was received on 5 June 2026, and your refund of ₹2,499 was initiated on 7 June 2026 to your UPI payment method. Refunds to UPI take 5–7 business days, so you should receive it by 14 June 2026."

Why it's correct: it references the exact status (`initiated`), the exact amount, the exact date, and the payment-method-specific timeline. The customer knows exactly where they stand and exactly what to expect.

---

**Bad AI answer:**

> "Your refund has already been completed. Please check your bank account."

Why it's dangerous: `refund_status = initiated`. The refund hasn't arrived. The customer stops following up. They wait 3 days. Then they call support, angry. Every one of those calls costs the business money that good evaluation would have prevented.

---

## 6. Failure Classification

I defined four failure labels. This was the hardest part of the build — not the code, but deciding where the boundaries are.

**Hallucinated**
The answer contradicts the data. The agent made a claim that isn't supported by what the backend returned.
*Risk level: High. Causes customers to take wrong actions.*

**Incomplete**
The answer is technically not wrong, but it's missing information the system had available. "Your refund has been initiated" when we also know the amount, date, and expected completion.
*Risk level: Medium. Customer calls back. Support cost rises.*

**Uncertain**
The answer is vague even though the data was present. The agent chose not to commit to an answer when it should have.
*Risk level: Medium. Wasted interaction. Customer trust erodes.*

**Grounded**
The answer matches the data. All key fields are present and accurate.
*Risk level: None. This is what we're aiming for.*

---

## 7. Metrics Calculation

**Sample dataset:** 15 conversations

| Label | Count | Rate |
|---|---|---|
| Grounded | 7 | 46.7% |
| Hallucinated | 3 | 20.0% |
| Incomplete | 3 | 20.0% |
| Uncertain | 2 | 13.3% |

```
Quality Score = 46.7 - (20.0 × 1.5) - (20.0 × 0.5) - (13.3 × 0.25)
              = 46.7 - 30.0 - 10.0 - 3.3
              = 3.4 / 100
```

**That score is the story.** A 3.4/100 means: don't ship this agent. Not without adding guardrails.

I designed the penalty formula deliberately. Hallucinations get a 1.5× multiplier because they cause direct customer harm. Incomplete answers get 0.5× — they're annoying, not catastrophic. Uncertain answers get 0.25× — they waste a touchpoint but don't actively mislead.

The formula is a product decision about risk tolerance, not just a math formula.

---

## 8. LangSmith Trace Analysis

I built a Trace Explorer tab that simulates what a LangSmith trace would show:

```
Step 1 — User Input
  → "Where is my refund?"

Step 2 — Intent Detection
  → intent: refund_status

Step 3 — Mock API Calls
  → get_order("ORD-4582")        → order_status: delivered
  → get_return_by_order(...)     → return_status: return_received
  → get_refund_by_order(...)     → refund_status: initiated
  → get_policy()                 → UPI: 5-7 business days

Step 4 — Answer Generation
  → "Your refund has already been completed..."
  → Label: Hallucinated
  → Reason: refund_status = initiated, not completed

Step 5 — Evaluation
  → Fix: Add data-validation gate
```

The trace makes root-cause analysis possible. Without it, you just see a bad answer. With it, you can pinpoint: the agent fetched the refund data correctly but the answer-generation step didn't check `refund_status` before using "completed" language.

That's a fixable prompt instruction, not a model problem.

---

## 9. Product / System Fixes

| Failure | Root Cause | Fix |
|---|---|---|
| Hallucinated refund status | Prompt doesn't enforce using `refund_status` field | Add pre-answer check: if `refund_status != completed`, never use "completed" language |
| Incomplete timeline | Prompt doesn't mandate including expected date | Add to system prompt: "Always include expected_completion_date when available" |
| Uncertain when data exists | Fallback triggers too early | Narrow fallback conditions to only trigger when `order_id` is genuinely missing |

**The principle I kept coming back to:** every AI failure here is a prompt/architecture decision that was never explicitly made, not a model intelligence problem. The model is capable of the right answer. It just wasn't instructed clearly enough.

---

## 10. Business Impact

If this agent handles 10,000 refund queries per month:

| Label | Volume | Avg Support Cost | Monthly Cost |
|---|---|---|---|
| Hallucinated (20%) | 2,000 | ₹600/escalation | ₹12,00,000 |
| Incomplete (20%) | 2,000 | ₹200/callback | ₹4,00,000 |
| Uncertain (13%) | 1,300 | ₹200/callback | ₹2,60,000 |
| **Total avoidable cost** | | | **₹18,60,000/month** |

Fixing hallucinations alone (from 20% to 5%) would save ~₹9 lakh/month at that scale.

The evaluation dashboard is not a monitoring tool. It's a cost-reduction instrument.

---

## 11. What I'd build next

1. **Real LangSmith integration** — connect `@traceable` decorator and compare simulated vs real LLM traces
2. **Human evaluation layer** — spot-check sample and compare human labels to automated labels (measure evaluator accuracy)
3. **Trend view** — hallucination rate by intent type, by time, to find which query categories are riskiest
4. **Prompt A/B test** — run two versions of the system prompt and compare their Quality Scores
5. **Cost model** — connect actual support ticket data to estimate real saved cost per label improvement

---

## What I learned

The thing that surprised me most: **writing the evaluator was harder than writing the agent.**

Deciding exactly when an answer is "hallucinated" vs "incomplete" vs "uncertain" forced me to define what "correct" actually means for each intent type. That's a product requirements exercise disguised as code.

The quality score formula was a similar exercise. The 1.5× hallucination penalty isn't arbitrary — it's a statement about which failure type the business least tolerates. Changing that multiplier changes the product's risk posture.

Every number in that formula is a product decision.

---

*Part of the AI PM transition portfolio. Builder loop: concept → build → break → fix → business impact → GitHub → case study → publish.*
