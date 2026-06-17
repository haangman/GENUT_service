"""drop unique on product name

Revision ID: 20e9e4efaf2c
Revises: 406e1798f687
Create Date: 2026-06-17 17:44:46.730062

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20e9e4efaf2c'
down_revision: Union[str, Sequence[str], None] = '406e1798f687'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 무명 unique 제약을 배치 모드에서 드롭하려면 결정적 이름이 필요하다(Alembic 권장 방식).
_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    """products.name의 unique 제약을 제거(동일 이름 허용)."""
    with op.batch_alter_table("products", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.drop_constraint("uq_products_name", type_="unique")


def downgrade() -> None:
    """unique 제약 복원."""
    with op.batch_alter_table("products", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.create_unique_constraint("uq_products_name", ["name"])
