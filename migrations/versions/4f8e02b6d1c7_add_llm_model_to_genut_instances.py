"""add llm_model to genut_instances

Revision ID: 4f8e02b6d1c7
Revises: 7be21d40c5a9
Create Date: 2026-07-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f8e02b6d1c7'
down_revision: Union[str, Sequence[str], None] = '7be21d40c5a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 기존 행 백필을 위해 server_default를 둔다(신규 행은 ORM 기본값 사용).
    with op.batch_alter_table('genut_instances', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('llm_model', sa.String(length=32), nullable=False, server_default='gptOss')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('genut_instances', schema=None) as batch_op:
        batch_op.drop_column('llm_model')
