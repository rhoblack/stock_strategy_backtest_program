"""MarketIndex 모델 (07번 §3 / 14번 §3-4 / 06번 §6).

KOSPI / KOSDAQ / KOSPI200 등 시장 지수의 일봉 시계열. 백테스트 벤치마크 비교
및 시장 지수 필터(예: KOSPI200 편입 종목만 거래)에 사용된다 (14번 §3-4).

본 step(027)에서는 다음을 보존한다:
    - index_code (KOSPI / KOSDAQ / KOSPI200 — 14번 §3-4)
    - date
    - open / high / low / close / volume
    - change_pct (전일 대비 등락률 — 외부 지수 데이터에서 직접 받거나 후속 처리에서 계산)

UniqueConstraint(index_code, date):
    동일 (index_code, date) 중복 방지.

인덱스 (index_code, date):
    벤치마크 시계열 조회에 사용. (date)는 단일 인덱스를 별도로 두지 않는다 —
    지수 종류 수가 적어 (date)만의 cross-section 조회는 드물다.

13.7 / 14.5 정합성:
    - 지수는 종목과 달리 corporate_action / 수정주가 개념이 적용되지 않는다 (지수 자체가
      이미 가중평균/수정 반영 결과). 따라서 본 모델은 `adj_*` 컬럼을 두지 않는다.
    - 단, 외부 데이터에 OHLC가 모두 들어오지 않는 경우(예: pykrx가 일부 지수의 high/low만
      제공하지 않는 경우)를 대비해 모든 OHLC를 NOT NULL로 강제하지 않고 NULL 허용.
      (수집기 / collector가 NOT NULL 강제는 별도 정책으로 결정 — 본 step은 모델만)

13.13 / 14.10 생존편향 / 결손 정책:
    - 지수에는 폐지 개념이 없으므로 listing/delisting 처리 불필요.
    - 결손 봉(거래소 휴장 외 누락)은 row 자체가 없음 — forward-fill 금지.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 14번 §3-4가 명시한 주요 지수. 본 enum은 application validation용
# (DB 측은 String으로 보존, 새 지수 추가 시 본 tuple만 갱신).
MARKET_INDEX_CODES: tuple[str, ...] = (
    "KOSPI",
    "KOSDAQ",
    "KOSPI200",
    "KOSDAQ150",
    "KRX100",
)


class MarketIndex(Base):
    """시장 지수 일봉 (KOSPI / KOSDAQ / KOSPI200 등).

    14번 §3-4 / 06번 §6: 벤치마크 비교 + 시장 지수 필터 입력.

    Args/필드:
        index_code: 14번 §3-4 enum 권장 (KOSPI / KOSDAQ / KOSPI200 / KOSDAQ150 / KRX100).
                    DB는 String이므로 새 지수 추가 시 MARKET_INDEX_CODES만 갱신.
        date: 거래일.
        open / high / low / close: 지수 OHLC. 외부 데이터 결손 가능성을 고려해 NULL 허용.
        volume: 지수 구성 종목 합산 거래량 (외부 제공 시).
        change_pct: 전일 대비 등락률(%) — 외부 데이터에서 직접 수신 또는 후속 계산.
        created_at: 본 row 생성 시각.
    """

    __tablename__ = "market_indices"
    __table_args__ = (
        UniqueConstraint(
            "index_code", "date",
            name="uq_market_indices_code_date",
        ),
        Index("ix_market_indices_code_date", "index_code", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    index_code: Mapped[str] = mapped_column(String(30), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)

    # 지수 OHLCV — 외부 데이터 결손 가능성을 고려해 NULL 허용
    # (수집기에서 NOT NULL 강제는 별도 정책)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float] = mapped_column(Float, nullable=False)  # close는 필수 (지수 자체값)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<MarketIndex {self.index_code} {self.date} close={self.close}>"
        )
