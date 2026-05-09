"""Alembic 환경 설정.

app.db.base.Base.metadata를 target으로 사용하여 모든 모델을 자동 인식.
URL은 alembic.ini에서 또는 ALEMBIC_DATABASE_URL 환경변수로 override 가능.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# backend/ 를 sys.path에 추가하여 app.* import 가능하게 함
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 모든 모델을 import해야 Base.metadata가 인식
from app.db.base import Base  # noqa: E402
import app.models  # noqa: F401, E402

# Alembic Config
config = context.config

# 로깅
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 환경변수로 URL override (CI / 운영 환경에서 사용)
env_url = os.getenv("ALEMBIC_DATABASE_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline 모드 (URL만으로 SQL script 출력)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url and url.startswith("sqlite"),  # SQLite ALTER 호환
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online 모드 (실제 DB 연결)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"

        if is_sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=False,  # batch mode가 일부 op.create_table을 silent skip시키는 이슈
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
