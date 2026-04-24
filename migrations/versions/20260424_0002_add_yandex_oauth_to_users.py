"""add yandex oauth to users

Revision ID: 20260424_0002
Revises: 20260421_0001
Create Date: 2026-04-24 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_0002"
down_revision = "20260421_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("yandex_user_id", sa.String(length=255), nullable=True))
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=True)
    op.alter_column("users", "password_salt", existing_type=sa.String(length=255), nullable=True)
    op.create_index("ix_users_yandex_user_id", "users", ["yandex_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_yandex_user_id", table_name="users")
    op.alter_column("users", "password_salt", existing_type=sa.String(length=255), nullable=False)
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("users", "yandex_user_id")
