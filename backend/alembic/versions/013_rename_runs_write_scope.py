"""Rename service key scope runs:write → runs:execute.

Revision ID: 013_rename_runs_write_scope
Revises: 012_hybrid_catalog_allowlists
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013_rename_runs_write_scope"
down_revision: str | None = "012_hybrid_catalog_allowlists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _remap_scopes(scopes: object, *, src: str, dst: str) -> list[str] | None:
    if isinstance(scopes, str):
        try:
            scopes = json.loads(scopes)
        except json.JSONDecodeError:
            return None
    if not isinstance(scopes, list):
        return None
    changed = False
    next_scopes: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        mapped = dst if scope == src else str(scope)
        if mapped in seen:
            changed = changed or scope == src
            continue
        seen.add(mapped)
        next_scopes.append(mapped)
        if mapped != scope:
            changed = True
    return next_scopes if changed else None


def _rewrite(src: str, dst: str) -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, scopes FROM service_keys")).fetchall()
    for row_id, scopes in rows:
        next_scopes = _remap_scopes(scopes, src=src, dst=dst)
        if next_scopes is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE service_keys SET scopes = CAST(:scopes AS json) WHERE id = :id"
            ),
            {"scopes": json.dumps(next_scopes), "id": row_id},
        )


def upgrade() -> None:
    _rewrite("runs:write", "runs:execute")


def downgrade() -> None:
    _rewrite("runs:execute", "runs:write")
