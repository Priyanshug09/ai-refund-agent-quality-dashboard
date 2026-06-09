"""
mock_data.py
------------
Simulated backend APIs for the AI Refund Agent.
In a real system, these would be calls to separate microservices.
Here, they're Python dicts — good enough to demonstrate the evaluation logic.

Decision I made: Use 5 distinct order scenarios so the dashboard shows
all failure types, not just a single happy-path loop.
"""

USERS = {
    "USER-101": {
        "user_id": "USER-101",
        "name": "Rahul Sharma",
        "email": "rahul.sharma@example.com",
        "account_status": "active"
    },
    "USER-102": {
        "user_id": "USER-102",
        "name": "Priya Patel",
        "email": "priya.patel@example.com",
        "account_status": "active"
    }
}

ORDERS = {
    "ORD-4582": {
        "order_id": "ORD-4582",
        "user_id": "USER-101",
        "product": "Running Shoes — Nike Air Max",
        "quantity": 1,
        "order_amount": 2499,
        "order_date": "2026-05-20",
        "order_status": "delivered",
        "delivery_date": "2026-05-26",
        "payment_method": "UPI",
        "currency": "INR"
    },
    "ORD-3891": {
        "order_id": "ORD-3891",
        "user_id": "USER-101",
        "product": "Wireless Headphones — Sony WH-1000XM5",
        "quantity": 1,
        "order_amount": 18999,
        "order_date": "2026-05-28",
        "order_status": "delivered",
        "delivery_date": "2026-06-01",
        "payment_method": "Credit Card",
        "currency": "INR"
    },
    "ORD-2244": {
        "order_id": "ORD-2244",
        "user_id": "USER-102",
        "product": "Bluetooth Speaker — JBL Flip 6",
        "quantity": 1,
        "order_amount": 8999,
        "order_date": "2026-05-10",
        "order_status": "delivered",
        "delivery_date": "2026-05-14",
        "payment_method": "Debit Card",
        "currency": "INR"
    },
    "ORD-5119": {
        "order_id": "ORD-5119",
        "user_id": "USER-102",
        "product": "Laptop Backpack — Wildcraft",
        "quantity": 1,
        "order_amount": 2499,
        "order_date": "2026-05-30",
        "order_status": "delivered",
        "delivery_date": "2026-06-03",
        "payment_method": "UPI",
        "currency": "INR"
    },
    "ORD-6670": {
        "order_id": "ORD-6670",
        "user_id": "USER-101",
        "product": "Smart Watch — Noise ColorFit Pro",
        "quantity": 1,
        "order_amount": 3499,
        "order_date": "2026-06-06",
        "order_status": "shipped",
        "delivery_date": None,
        "payment_method": "UPI",
        "currency": "INR"
    }
}

RETURNS = {
    "RET-4582": {
        "return_id": "RET-4582",
        "order_id": "ORD-4582",
        "return_reason": "Wrong size",
        "return_status": "return_received",
        "return_requested_date": "2026-06-01",
        "return_pickup_date": "2026-06-03",
        "return_received_date": "2026-06-05",
        "return_condition": "good"
    },
    "RET-3891": {
        "return_id": "RET-3891",
        "order_id": "ORD-3891",
        "return_reason": "Defective product — audio cuts out",
        "return_status": "pickup_scheduled",
        "return_requested_date": "2026-06-05",
        "return_pickup_date": "2026-06-10",
        "return_received_date": None,
        "return_condition": None
    },
    "RET-2244": {
        "return_id": "RET-2244",
        "order_id": "ORD-2244",
        "return_reason": "Not as described",
        "return_status": "return_received",
        "return_requested_date": "2026-05-18",
        "return_pickup_date": "2026-05-20",
        "return_received_date": "2026-05-22",
        "return_condition": "good"
    },
    "RET-5119": {
        "return_id": "RET-5119",
        "order_id": "ORD-5119",
        "return_reason": "Item damaged during delivery",
        "return_status": "return_received",
        "return_requested_date": "2026-06-04",
        "return_pickup_date": "2026-06-06",
        "return_received_date": "2026-06-07",
        "return_condition": "damaged"  # <-- triggers partial refund
    }
}

REFUNDS = {
    "REF-4582": {
        "refund_id": "REF-4582",
        "order_id": "ORD-4582",
        "refund_status": "initiated",           # NOT completed — key fact for hallucination tests
        "refund_amount": 2499,
        "refund_initiated_date": "2026-06-07",
        "refund_completed_date": None,
        "expected_completion_date": "2026-06-14",
        "refund_type": "full",
        "payment_method": "UPI"
    },
    "REF-2244": {
        "refund_id": "REF-2244",
        "order_id": "ORD-2244",
        "refund_status": "completed",
        "refund_amount": 8999,
        "refund_initiated_date": "2026-05-23",
        "refund_completed_date": "2026-05-26",
        "expected_completion_date": "2026-05-29",
        "refund_type": "full",
        "payment_method": "Debit Card"
    },
    "REF-5119": {
        "refund_id": "REF-5119",
        "order_id": "ORD-5119",
        "refund_status": "initiated",
        "refund_amount": 1249,                  # Partial — item was returned damaged
        "refund_initiated_date": "2026-06-08",
        "refund_completed_date": None,
        "expected_completion_date": "2026-06-15",
        "refund_type": "partial",
        "payment_method": "UPI",
        "partial_refund_reason": "Item returned in damaged condition. Per policy, 50% refund applied."
    }
}

REFUND_POLICY = {
    "standard_return_window": "10 days from delivery",
    "refund_timelines": {
        "UPI": "5-7 business days after refund initiation",
        "Credit Card": "7-10 business days after refund initiation",
        "Debit Card": "5-7 business days after refund initiation",
        "Net Banking": "3-5 business days after refund initiation",
        "COD": "7-10 business days via bank transfer"
    },
    "partial_refund_conditions": [
        "Item returned in damaged condition: 50% refund",
        "Missing accessories: deduction per item",
        "Signs of use on electronics: 20% deduction"
    ],
    "non_refundable_conditions": [
        "Items returned after 10-day window",
        "Items with broken seals (hygiene products)",
        "Customised or personalised items"
    ],
    "cancellation_policy": {
        "before_shipping": "Full refund within 24 hours.",
        "after_shipping": "Cannot cancel. Wait for delivery, then initiate return within 10 days.",
        "out_for_delivery": "Refuse delivery at doorstep and contact support."
    }
}


# ── API-style accessor functions ───────────────────────────────────────────────

def get_order(order_id: str):
    return ORDERS.get(order_id)

def get_return_by_order(order_id: str):
    return next((r for r in RETURNS.values() if r["order_id"] == order_id), None)

def get_refund_by_order(order_id: str):
    return next((r for r in REFUNDS.values() if r["order_id"] == order_id), None)

def get_user(user_id: str):
    return USERS.get(user_id)

def get_policy():
    return REFUND_POLICY
