"""add job kind/origin and product auto tracking fields

Revision ID: c3d94a17be02
Revises: 8fbadfbbd173
Create Date: 2026-07-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d94a17be02'
down_revision: Union[str, Sequence[str], None] = '8fbadfbbd173'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 기존 행 백필을 위해 NOT NULL 컬럼엔 server_default를 둔다(신규 행은 ORM 기본값 사용).
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('kind', sa.String(length=16), nullable=False, server_default='genut')
        )
        batch_op.add_column(
            sa.Column('origin', sa.String(length=16), nullable=False, server_default='manual')
        )

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('last_auto_run_at', sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column('last_scanned_commit', sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('last_scanned_commit')
        batch_op.drop_column('last_auto_run_at')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('origin')
        batch_op.drop_column('kind')
