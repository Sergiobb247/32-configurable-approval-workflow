"""The end-to-end demo path, asserted against the frozen contracts.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/test-plan.md §4.8 — "login → create workflow → create request
→ submit → approve ×3 → APPROVED, and GET /requests/{id}/audit returns
≥ 5 ordered rows".

This suite drives the product exactly the way the demo does, through the
real HTTP API. It is written against the FROZEN contracts and must pass
against the integrated app (A's auth, C's engine, D's workflow/audit
routes); if it fails, the bug is in whoever broke the contract, not here.

A note on the chain: it ends in a MANAGER step held by a SECOND manager, not
an ADMIN. The frozen permission rule is absolute — "an admin cannot approve
a single request" (explanation.md §5, failure path #12, test-plan §4.5) —
while docs/app-flow.md §4 still sketches a demo ending in an ADMIN step.
That doc tension is flagged to the team; this test follows the rule that
keeps the headline claim true: nobody can manufacture an approval.
"""

from __future__ import annotations

import factories

CHAIN = [
    {"step_order": 1, "required_role": "MANAGER", "label": "Line manager"},
    {"step_order": 2, "required_role": "FINANCE", "label": "Finance review"},
    {"step_order": 3, "required_role": "MANAGER", "label": "Second manager"},
]


def test_full_approval_cycle_end_to_end(db, client, auth_headers):
    # --- the cast (mirrors the seed users in schema.md §6) ------------------
    admin = factories.make_user(db, role="ADMIN", email="admin@demo.io")
    manager1 = factories.make_user(db, role="MANAGER", email="manager1@demo.io")
    factories.make_user(db, role="MANAGER", email="manager2@demo.io")
    factories.make_user(db, role="FINANCE", email="finance@demo.io")
    employee = factories.make_user(db, role="EMPLOYEE", email="employee1@demo.io")

    admin_h = auth_headers(email=admin.email)
    manager1_h = auth_headers(email=manager1.email)
    manager2_h = auth_headers(email="manager2@demo.io")
    finance_h = auth_headers(email="finance@demo.io")
    employee_h = auth_headers(email=employee.email)

    # --- 1. admin configures the chain --------------------------------------
    r = client.post(
        "/workflows",
        json={
            "name": "Expense approval",
            "description": "Manager, finance, second manager",
            "steps": CHAIN,
        },
        headers=admin_h,
    )
    assert r.status_code == 201, r.text
    workflow_id = r.json()["id"]
    assert [s["step_order"] for s in r.json()["steps"]] == [1, 2, 3]

    # --- 2. employee drafts and submits ₦450,000 ----------------------------
    r = client.post(
        "/requests",
        json={
            "workflow_id": workflow_id,
            "title": "Laptop replacement",
            "description": "MacBook died",
            "amount": "450000.00",
        },
        headers=employee_h,
    )
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    assert r.json()["status"] == "DRAFT"

    r = client.post(f"/requests/{request_id}/submit", headers=employee_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["current_step_index"] == 0
    # the chain is frozen onto the request (the snapshot rule, schema.md §4.5)
    assert [(s["order"], s["role"]) for s in body["steps"]] == [
        (1, "MANAGER"),
        (2, "FINANCE"),
        (3, "MANAGER"),
    ]

    # --- 3. the chain is walked by three DIFFERENT approvers ----------------
    approvers = [
        (manager1_h, 1),                      # step 1 -> moves to step 2
        (finance_h, 2),                       # step 2 -> moves to step 3
        (manager2_h, None),                   # step 3 -> APPROVED (final)
    ]
    for headers, next_step in approvers:
        r = client.post(
            f"/requests/{request_id}/approve",
            json={"comment": "Approved, within budget"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if next_step is None:
            assert body["status"] == "APPROVED"
            assert body["decided_at"] is not None
        else:
            assert body["status"] == "PENDING"
            assert body["current_step_index"] == next_step

    # --- 4. the audit trail matches the actions, in order -------------------
    r = client.get(f"/requests/{request_id}/audit", headers=employee_h)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert r.json()["total"] == len(items)
    assert len(items) >= 5, f"expected at least 5 audit rows, got: {items}"

    actions = [row["action"] for row in items]
    # submitted once, then exactly three approvals, most recent last
    assert actions[-4:] == ["SUBMITTED", "APPROVED", "APPROVED", "APPROVED"]
    # a timeline: ascending, with id as tie-breaker (schema.md §4.6)
    assert items == sorted(items, key=lambda row: (row["created_at"], row["id"]))
    # every row says who did it
    assert all(row["actor"]["full_name"] for row in items)
