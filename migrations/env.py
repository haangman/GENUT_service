"""Alembic 마이그레이션 환경.

DB_URL은 alembic.ini가 아니라 애플리케이션 설정(genut_service.config)에서 가져온다.
모델 메타데이터는 genut_service.db.base.Base에 등록된다.
(M1에서 models 모듈을 추가하면 아래 import를 활성화하여 autogenerate가 동작한다.)
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from genut_service.config import get_settings
from genut_service.db.base import Base

# 모델을 import 하여 Base.metadata에 등록한다(autogenerate 대상)
import genut_service.db.models  # noqa: F401,E402

config = context.config

# 애플리케이션 설정의 DB_URL로 덮어쓴다
config.set_main_option("sqlalchemy.url", get_settings().db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인(URL만) 모드."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인(Engine 연결) 모드."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
