"""CorporateAction 모델 (07번 §12-B / 06번 §6 / 14번 §9 / 14번 §15).

분할/병합/배당/유증 등 권리 이력. 신규 corporate_action 수집 시 영향 종목의
수정주가를 과거 전체 재계산해야 한다 (14.9, 13.7).

본 step(026)에서는 다음을 보존한다:
    - symbol (FK → symbols.symbol, ON DELETE CASCADE)
    - event_date (권리락 발생일 — 본 일자 이전 가격을 재계산해야 함)
    - event_type (split / cash_dividend / bonus_issue / rights_issue / merger / spinoff /
                  delisting — 14번 §15 enum)
    - ratio (분할/병합/무상증자/유상증자 비율 — split=신주/구주, cash_dividend는 사용 안 함)
    - dividend_amount (현금 배당 주당 배당금 — cash_dividend 외에는 NULL)
    - notes (자유 텍스트, 데이터 출처 보강 메모용)

UniqueConstraint(symbol, event_date, event_type):
    동일 일자에 split + cash_dividend가 동시에 일어날 수 있으므로 (event_type까지) 복합 unique.

인덱스 (symbol, event_date):
    AdjustedPriceProcessor가 종목별 시간 역순으로 적용 — 본 인덱스로 효율적 조회.

13.13 / 14.10 정합성:
    - delisting_date 정보는 symbols.delisting_date가 단일 출처
    - 본 모델에서 event_type='delisting' row를 가질 수 있지만 symbols.delisting_date와
      충돌 시 symbols 측이 우선 (UniverseSelector는 symbols만 봄)

13.7 정합성:
    - 본 모델은 corporate_action 사실 자체만 보존
    - adj_* 재계산은 AdjustedPriceProcessor (data_pipeline/processors/adjusted_price.py) 책임
    - close (원 가격)는 corporate_action 영향 없음
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.symbol import Symbol


# 14번 §15 event_type enum (DB 측에서는 String으로 보존, 애플리케이션이 검증)
CORPORATE_ACTION_EVENT_TYPES: tuple[str, ...] = (
    "split",            # 액면분할 (1주 → ratio주)
    "reverse_split",    # 액면병합 (ratio주 → 1주)
    "bonus_issue",      # 무상증자 (보유 1주당 ratio주 추가)
    "rights_issue",     # 유상증자 (이론권리락)
    "cash_dividend",    # 현금 배당 (dividend_amount 사용)
    "merger",           # 합병 (본 step에서는 정책 단순화 — Processor가 NotImplementedError)
    "spinoff",          # 분할 (본 step에서는 정책 단순화)
    "delisting",        # 상장폐지 (참고용 — symbols.delisting_date가 단일 출처)
)


class CorporateAction(Base):
    """corporate_actions 테이블.

    AdjustedPriceProcessor의 입력으로 사용된다 (시간 역순으로 가격 보정).

    필수: symbol / event_date / event_type / ratio (cash_dividend는 dividend_amount 사용,
    ratio는 0.0 또는 1.0).

    Args/필드:
        symbol: 6자리 종목코드 (FK).
        event_date: 권리락 발생일 (본 일자의 가격은 이미 권리락 반영, 본 일자 *이전*을 재계산).
        event_type: 14번 §15 enum.
        ratio: split=신주/구주(예 1:2 → 2.0), reverse_split=구주/신주, bonus_issue=비율,
               rights_issue=비율, 그 외 = 0.0 또는 1.0 (사용 안 함).
        dividend_amount: cash_dividend 주당 배당금. 그 외에는 NULL.
        notes: 자유 텍스트 메모.
        created_at: 본 row 생성 시각.
    """

    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "event_date", "event_type",
            name="uq_corporate_actions_symbol_date_type",
        ),
        Index("ix_corporate_actions_symbol_event_date", "symbol", "event_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("symbols.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    event_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # split / bonus_issue / rights_issue / reverse_split 등에서 사용. cash_dividend는 0.0.
    ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # cash_dividend 주당 배당금. 그 외에는 NULL.
    dividend_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 관계: 종목
    symbol_ref: Mapped[Symbol] = relationship(back_populates="corporate_actions")

    def __repr__(self) -> str:
        if self.event_type == "cash_dividend":
            extra = f"dividend={self.dividend_amount}"
        else:
            extra = f"ratio={self.ratio}"
        return (
            f"<CorporateAction {self.symbol} {self.event_date} {self.event_type} {extra}>"
        )
