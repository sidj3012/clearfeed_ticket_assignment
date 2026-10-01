"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
# Alembic fills in the revision metadata and operation blocks when generating a migration.
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}


revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${"pass" if not upgrades else upgrades}


def downgrade() -> None:
    ${"pass" if not downgrades else downgrades}
