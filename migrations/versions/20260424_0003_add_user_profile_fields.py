"""add user profile fields

Revision ID: 20260424_0003
Revises: 20260424_0002
Create Date: 2026-04-24 20:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_0003"
down_revision = "20260424_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.add_column("users", sa.Column("region_code", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("last_device_type", sa.String(length=32), nullable=True))
    op.create_index("ix_users_country_code_region_code", "users", ["country_code", "region_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_country_code_region_code", table_name="users")
    op.drop_column("users", "last_device_type")
    op.drop_column("users", "birth_date")
    op.drop_column("users", "region_code")
    op.drop_column("users", "country_code")
