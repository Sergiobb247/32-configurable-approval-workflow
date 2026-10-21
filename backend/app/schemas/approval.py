"""Approve / reject bodies — TWO models, on purpose.

Owner: Person B — Domain & Contracts (Saviour Menebari Peba).
Contract: docs/technical-spec.md §7.5 and decision log #2.

The reject comment is REQUIRED and the approve comment is OPTIONAL. Two
separate models mean OpenAPI marks the reject comment as required, the
frontend knows the rule before it builds the form, and a blank rejection is
a 422 from validation — not a hand-written `if` in a route. The engine keeps
a one-line assertion as a backstop for non-HTTP callers (spec §7.5).
"""

from __future__ import annotations

from pydantic import field_validator

from .common import ApiModel

_COMMENT_LIMIT = "Comments are limited to 500 characters"


class ApproveIn(ApiModel):
    """POST /requests/{id}/approve — comment optional, max 500 chars.
    A comment that is blank after trimming is stored as null."""

    comment: str | None = None

    @field_validator("comment")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 500:
            raise ValueError(_COMMENT_LIMIT)
        return value


class RejectIn(ApiModel):
    """POST /requests/{id}/reject — comment REQUIRED, 1–500 chars after
    trim. The validator message is the verbatim catalogue sentence
    (technical-spec.md §8) so the 422 reads the same everywhere."""

    comment: str

    @field_validator("comment")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A comment is required when rejecting")
        if len(value) > 500:
            raise ValueError(_COMMENT_LIMIT)
        return value
