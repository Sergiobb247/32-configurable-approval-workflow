"""Unit + API tests for the audit trail (Endpoints 21–22 and `record()`).

Owner: Person D — Workflows, Audit & Ops (Moses Abigail).
Contract: docs/test-plan.md §4.7, docs/schema.md §4.6,
docs/technical-spec.md §2 (one-writer rule), §7.6, docs/prd.md US-12.

Naming convention: `test_<behaviour>_<condition>_<expected>` (test-plan.md §2).

The decisive tests here are the first two: they prove `audit.record()`
flushes but never commits. If `record()` committed on its own, a rollback
after it could not remove the row — and the trail could describe a state
change that never happened. Row-then-rollback is the only honest way to
test that, so that is exactly what they do.
"""

from __future__ import annotations

import factories
from app.models import AuditAction, AuditLog, EntityType, Role
from app.services import audit


def test_record_when_called_writes_row_visible_after_caller_commits(db):
    actor = factories.make_user(db, email="actor@demo.io")
    request = factories.make_request(db, submitter=actor)

    entry = audit.record(
        db,
        actor=actor,
        action=AuditAction.SUBMITTED,
        entity_type=EntityType.REQUEST,
        entity_id=request.id,
        request_id=request.id,
        from_state="DRAFT",
        to_state="PENDING",
    )

    # Flushed: the row exists inside the transaction and already has an id
    # and timestamp, before anyone has committed anything.
    assert entry.id is not None
    assert entry.created_at is not None
    assert entry.actor_id == actor.id
    assert entry.action == "SUBMITTED"

    db.commit()
    assert db.query(AuditLog).filter_by(request_id=request.id).count() == 1


def test_record_when_transaction_rolls_back_leaves_no_audit_row(db):
    actor = factories.make_user(db, email="rollback@demo.io")
    request = factories.make_request(db, submitter=actor)

    audit.record(
        db,
        actor=actor,
        action=AuditAction.APPROVED,
        entity_type=EntityType.REQUEST,
        entity_id=request.id,
        request_id=request.id,
        from_state="PENDING",
        to_state="APPROVED",
    )
    # The entry is visible in-transaction (it was flushed)...
    assert db.query(AuditLog).filter_by(request_id=request.id).count() == 1

    # ...but record() never committed, so rolling the transaction back takes
    # the phantom approval record with it. The trail cannot lie.
    db.rollback()
    assert db.query(AuditLog).filter_by(request_id=request.id).count() == 0


def _write_decision_sequence(db, *, submitter, manager, finance, request):
    """SUBMITTED -> APPROVED -> REJECTED, recorded via the one writer."""
    audit.record(
        db,
        actor=submitter,
        action=AuditAction.SUBMITTED,
        entity_type=EntityType.REQUEST,
        entity_id=request.id,
        request_id=request.id,
        from_state="DRAFT",
        to_state="PENDING",
    )
    audit.record(
        db,
        actor=manager,
        action=AuditAction.APPROVED,
        entity_type=EntityType.REQUEST,
        entity_id=request.id,
        request_id=request.id,
        from_state="PENDING",
        to_state="PENDING",
        comment="Within budget",
    )
    audit.record(
        db,
        actor=finance,
        action=AuditAction.REJECTED,
        entity_type=EntityType.REQUEST,
        entity_id=request.id,
        request_id=request.id,
        from_state="PENDING",
        to_state="REJECTED",
        comment="Over budget this quarter",
    )
    db.commit()


def _cast(db):
    submitter = factories.make_user(
        db, email="employee1@demo.io", role=Role.EMPLOYEE, full_name="Ada Obi"
    )
    manager = factories.make_user(
        db, email="manager1@demo.io", role=Role.MANAGER, full_name="Bola Ade"
    )
    finance = factories.make_user(
        db, email="finance@demo.io", role=Role.FINANCE, full_name="Ngozi Eze"
    )
    request = factories.make_request(
        db, submitter=submitter, status="PENDING", current_step_index=1
    )
    return submitter, manager, finance, request


def test_request_audit_when_entries_exist_returns_them_oldest_first(
    db, client, auth_headers
):
    submitter, manager, finance, request = _cast(db)
    _write_decision_sequence(
        db, submitter=submitter, manager=manager, finance=finance, request=request
    )

    response = client.get(
        f"/requests/{request.id}/audit",
        headers=auth_headers(email=submitter.email),
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    # A timeline: ascending by created_at, then id as the tie-breaker (§4.6).
    assert items == sorted(items, key=lambda row: (row["created_at"], row["id"]))
    assert [row["id"] for row in items] == sorted(row["id"] for row in items)


def test_request_audit_after_submit_approve_reject_matches_expected_sequence(
    db, client, auth_headers
):
    submitter, manager, finance, request = _cast(db)
    _write_decision_sequence(
        db, submitter=submitter, manager=manager, finance=finance, request=request
    )

    response = client.get(
        f"/requests/{request.id}/audit",
        headers=auth_headers(email=submitter.email),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert [
        (row["action"], row["from_state"], row["to_state"]) for row in body["items"]
    ] == [
        ("SUBMITTED", "DRAFT", "PENDING"),
        ("APPROVED", "PENDING", "PENDING"),
        ("REJECTED", "PENDING", "REJECTED"),
    ]
    # Who and what they said travels with every row (§7.6 shape).
    assert body["items"][1]["actor"] == {"id": manager.id, "full_name": "Bola Ade"}
    assert body["items"][2]["comment"] == "Over budget this quarter"


def test_audit_when_routes_inspected_exposes_no_update_or_delete(
    client, auth_headers
):
    # Inspect the published OpenAPI surface (what a judge sees at /docs):
    # exactly the audit paths, and only GET on each of them.
    paths = client.get("/openapi.json").json()["paths"]
    audit_paths = {p: ops for p, ops in paths.items() if "audit" in p}

    # Exactly two read endpoints and zero write endpoints (§4.6, US-12).
    assert sorted(audit_paths) == ["/audit", "/requests/{request_id}/audit"]
    for _path, operations in audit_paths.items():
        assert set(operations) == {"get"}

    # And the running API agrees: write verbs get no handler.
    admin_h = auth_headers(role=Role.ADMIN)
    assert client.delete("/audit/1", headers=admin_h).status_code in (404, 405)
    assert (
        client.patch("/requests/1/audit", json={}, headers=admin_h).status_code
        in (404, 405)
    )


def test_request_audit_when_unrelated_employee_returns_403(
    db, client, auth_headers
):
    _submitter, _manager, _finance, request = _cast(db)
    stranger = factories.make_user(
        db, email="employee2@demo.io", role=Role.EMPLOYEE
    )

    response = client.get(
        f"/requests/{request.id}/audit",
        headers=auth_headers(email=stranger.email),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "This request belongs to someone else"


def test_request_audit_when_unknown_request_returns_404(client, auth_headers):
    response = client.get(
        "/requests/999999/audit", headers=auth_headers(role=Role.ADMIN)
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Request not found"


def test_global_audit_when_admin_returns_detail_newest_first(
    db, client, auth_headers
):
    submitter, manager, finance, request = _cast(db)
    _write_decision_sequence(
        db, submitter=submitter, manager=manager, finance=finance, request=request
    )

    response = client.get("/audit", headers=auth_headers(role=Role.ADMIN))

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [row["action"] for row in items] == ["REJECTED", "APPROVED", "SUBMITTED"]
    # The global feed adds which entity each row belongs to (§7.6 detail).
    assert items[0]["request_id"] == request.id
    assert items[0]["entity_type"] == "request"
    assert items[0]["entity_id"] == request.id


def test_global_audit_when_non_admin_returns_403(client, auth_headers):
    response = client.get("/audit", headers=auth_headers(role=Role.MANAGER))

    assert response.status_code == 403
    assert response.json()["detail"] == "Your role cannot do this"
