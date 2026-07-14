"""add project to products

Revision ID: a7d3c91e5b02
Revises: b069b8e28222
Create Date: 2026-07-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3c91e5b02'
down_revision: Union[str, Sequence[str], None] = 'b069b8e28222'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 기존 행은 기본 프로젝트(Ulysses)로 백필한다(신규 행은 ORM 기본값 사용).
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('project', sa.String(length=32), nullable=False, server_default='Ulysses')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('project')
