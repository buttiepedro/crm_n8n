"""Convierte leads.external_key de UNIQUE global a UNIQUE parcial (solo
entre leads vivos, deleted_at IS NULL). Sin esto, borrar un lead y que n8n
reenvíe el mismo externalKey en un webhook posterior rompía la creación del
lead nuevo por violar la unicidad contra el registro borrado.

Revision ID: 0010_lead_external_key_uniq
Revises: 0009_lead_archived_at
Create Date: 2026-07-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_lead_external_key_uniq"
down_revision: Union[str, None] = "0009_lead_archived_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("leads_external_key_key", "leads", type_="unique")
    op.create_index(
        "uq_leads_external_key_active",
        "leads",
        ["external_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_leads_external_key_active", table_name="leads")
    op.create_unique_constraint("leads_external_key_key", "leads", ["external_key"])
