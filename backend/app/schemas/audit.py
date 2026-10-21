"""Audit shapes (endpoints 21–22, Person D's routes; B's contract).

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §7.6, docs/schema.md §4.6.

There are no write schemas for audit on purpose: the trail is append-only,
written only by services/audit.record(). If it has an input schema, someone
can edit it. These are read shapes only.

* AuditEntryOut       — the per-request timeline (§7.6 example shape, exact)
* AuditEntryDetailOut — the admin global feed adds which request/entity the
                        row belongs to, since there it is not implied by the URL
"""

from __future__ import annotations

from pydantic import Field

from .common import ApiModel, ListResponse, UTCDateTime
from .user import ActorSummary


class AuditEntryOut(ApiModel):
    id: int
    action: str
    # Nested {id, full_name}, read from the ORM `actor` relationship.
    actor: ActorSummary
    from_state: str | None
    to_state: str | None
    comment: str | None
    created_at: UTCDateTime


class AuditEntryDetailOut(AuditEntryOut):
    request_id: int | None
    entity_type: str
    entity_id: int


AuditList = ListResponse[AuditEntryOut]
AuditDetailList = ListResponse[AuditEntryDetailOut]
