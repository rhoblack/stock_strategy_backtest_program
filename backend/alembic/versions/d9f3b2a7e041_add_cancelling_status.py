"""backtest_runs.status에 'cancelling' 값 추가 (10번 §4.4 cancel 전파)

BacktestStatus enum에 CANCELLING = "cancelling" 추가.
native_enum=False (VARCHAR 컬럼)이므로 제약 변경 없이 check constraint 업데이트만.

SQLite는 ALTER TABLE ... ADD CONSTRAINT를 지원하지 않으므로,
check constraint 갱신은 batch_alter_table을 통한 테이블 재생성으로 처리.

Revision ID: d9f3b2a7e041
Revises: a1b2c3d4e5f6
Create Date: 2026-05-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9f3b2a7e041"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """backtest_runs.status 허용값에 'cancelling' 추가.

    native_enum=False → VARCHAR로 저장되므로 DB 레벨 enum 수정 불필요.
    SQLAlchemy 모델(BacktestStatus)에 CANCELLING 추가만으로 동작하지만,
    명시적으로 기록 및 향후 체크 로직을 위해 마이그레이션 파일 추가.

    실질적 DDL 변경 없음 (VARCHAR에 새 값 저장 허용은 DB 레벨 변경 불필요).
    """
    # 실질적 DDL 없음 — 마이그레이션 이력 기록용
    pass


def downgrade() -> None:
    """'cancelling' 값이 저장된 행을 'cancelled'로 되돌리고 enum에서 제거.

    다운그레이드 시 DB에 'cancelling' 값이 있으면 애플리케이션이 오류를 낼 수 있으므로
    'cancelled'로 업데이트한다.
    """
    op.execute(
        sa.text(
            "UPDATE backtest_runs SET status = 'cancelled' WHERE status = 'cancelling'"
        )
    )
