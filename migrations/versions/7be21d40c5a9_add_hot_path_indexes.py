"""add hot-path indexes on jobs and job_events

Revision ID: 7be21d40c5a9
Revises: c3d94a17be02
Create Date: 2026-07-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7be21d40c5a9'
down_revision: Union[str, Sequence[str], None] = 'c3d94a17be02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 스케줄러 1초 틱(claim: status+kind, 배타: product_id+status)과
    # 이력/로그 폴링(origin, job_id+id)이 도는 핫패스 인덱스.
    op.create_index('ix_jobs_status_kind', 'jobs', ['status', 'kind'])
    op.create_index('ix_jobs_product_status', 'jobs', ['product_id', 'status'])
    op.create_index('ix_jobs_origin', 'jobs', ['origin'])
    op.create_index('ix_job_events_job_id_id', 'job_events', ['job_id', 'id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_job_events_job_id_id', table_name='job_events')
    op.drop_index('ix_jobs_origin', table_name='jobs')
    op.drop_index('ix_jobs_product_status', table_name='jobs')
    op.drop_index('ix_jobs_status_kind', table_name='jobs')
