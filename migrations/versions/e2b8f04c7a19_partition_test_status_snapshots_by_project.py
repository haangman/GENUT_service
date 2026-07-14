"""partition test_status_snapshots by project

Revision ID: e2b8f04c7a19
Revises: a7d3c91e5b02
Create Date: 2026-07-14 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b8f04c7a19'
down_revision: Union[str, Sequence[str], None] = 'a7d3c91e5b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 스냅샷은 파생 데이터라 drop/recreate가 안전하다 — 백그라운드 리프레셔가
    # 다음 주기에 (project, name) 키로 재계산하고, 부재 시 API는 실시간 스캔 폴백.
    op.drop_table('test_status_snapshots')
    op.create_table('test_status_snapshots',
    sa.Column('project', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('fingerprint', sa.String(length=2048), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('project', 'name')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('test_status_snapshots')
    op.create_table('test_status_snapshots',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('fingerprint', sa.String(length=2048), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )
