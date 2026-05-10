"""금액 컬럼을 REAL → INTEGER로 변환 (정확성 정책 §14)

한국 주식 금액은 항상 정수(원 단위)이므로 float → int 전환.
비율 필드(return_pct, fee_rate, drawdown 등)는 float 유지.

변환 대상:
  trade_groups:   entry_price, final_profit
  trade_executions: price, gross_amount, fee, tax, net_amount, realized_profit
  daily_equity:   cash, stock_value, total_equity
  cash_events:    cash_before, required_cash, cash_after, sell_amount,
                  exec_price, gross_amount, fee, tax, net_amount
  backtest_runs:  initial_cash
  backtest_results: initial_cash, final_equity

SQLite에서 컬럼 타입 변경은 batch_alter_table을 통한 테이블 재생성이 필요.
기존 데이터는 CAST(value AS INTEGER) — 소수점이 없는 KRW값이므로 정보 손실 없음.

Revision ID: a1b2c3d4e5f6
Revises: b5e8d3c1a924
Create Date: 2026-05-10 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "59cda024ecf8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === trade_groups ===
    with op.batch_alter_table("trade_groups") as batch_op:
        batch_op.alter_column(
            "entry_price",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "final_profit",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )

    # === trade_executions ===
    with op.batch_alter_table("trade_executions") as batch_op:
        batch_op.alter_column(
            "price",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "gross_amount",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "fee",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "tax",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "net_amount",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "realized_profit",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )

    # === daily_equity ===
    with op.batch_alter_table("daily_equity") as batch_op:
        batch_op.alter_column(
            "cash",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "stock_value",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "total_equity",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    # === cash_events ===
    with op.batch_alter_table("cash_events") as batch_op:
        batch_op.alter_column(
            "cash_before",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "required_cash",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "cash_after",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "sell_amount",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "exec_price",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "gross_amount",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "fee",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "tax",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "net_amount",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )

    # === backtest_runs ===
    with op.batch_alter_table("backtest_runs") as batch_op:
        batch_op.alter_column(
            "initial_cash",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    # === backtest_results ===
    with op.batch_alter_table("backtest_results") as batch_op:
        batch_op.alter_column(
            "initial_cash",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "final_equity",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )


def downgrade() -> None:
    # === backtest_results ===
    with op.batch_alter_table("backtest_results") as batch_op:
        batch_op.alter_column(
            "final_equity",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "initial_cash",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )

    # === backtest_runs ===
    with op.batch_alter_table("backtest_runs") as batch_op:
        batch_op.alter_column(
            "initial_cash",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )

    # === cash_events ===
    with op.batch_alter_table("cash_events") as batch_op:
        for col in ("net_amount", "tax", "fee", "gross_amount", "exec_price",
                    "sell_amount", "cash_after", "required_cash", "cash_before"):
            batch_op.alter_column(
                col,
                existing_type=sa.Integer(),
                type_=sa.Float(),
                existing_nullable=(col not in ("cash_before", "cash_after")),
            )

    # === daily_equity ===
    with op.batch_alter_table("daily_equity") as batch_op:
        for col in ("total_equity", "stock_value", "cash"):
            batch_op.alter_column(
                col,
                existing_type=sa.Integer(),
                type_=sa.Float(),
                existing_nullable=False,
            )

    # === trade_executions ===
    with op.batch_alter_table("trade_executions") as batch_op:
        for col, nullable in [
            ("realized_profit", True),
            ("net_amount", False),
            ("tax", False),
            ("fee", False),
            ("gross_amount", False),
            ("price", False),
        ]:
            batch_op.alter_column(
                col,
                existing_type=sa.Integer(),
                type_=sa.Float(),
                existing_nullable=nullable,
            )

    # === trade_groups ===
    with op.batch_alter_table("trade_groups") as batch_op:
        batch_op.alter_column(
            "final_profit",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "entry_price",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )
