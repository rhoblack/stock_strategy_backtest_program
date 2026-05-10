"""PriceLoader — repositories.get_price_range를 BacktestEngine 입력 DataFrame으로 변환.

설계 출처:
    - 06번 §3 / §12: PriceLoader 위치
    - 14번 §12 (백테스트 실행 시 데이터 로드)
    - 13번 §7 (수정주가) / §13.15 (look-ahead bias)
    - 작업로그/2026-05-10-015-* (BacktestEngine next_* 정합)

BacktestEngine이 기대하는 DataFrame 명세 (015 정합 + engine.py 검증):
    필수 컬럼:
        date            : datetime64 또는 date (오름차순)
        open / high / low / close / volume          (원 가격, 거래대금 필터용)
        adj_open / adj_high / adj_low / adj_close   (가격 조건 / 체결 기본 — 13.7)
        adj_volume                                  (수정 거래량)
    파생 (next_*) 컬럼 (PriceLoader가 자동 채움 — 015 정합):
        next_open       = adj_open.shift(-1)
        next_close      = adj_close.shift(-1)
        next_volume     = adj_volume.shift(-1)
        next_date       = date.shift(-1)
        adj_next_open   = next_open과 동일 (ExecutionModel.get_entry_price 호환용)
        adj_next_close  = next_close와 동일 (ExecutionModel.get_entry_price 호환용)
    선택 컬럼:
        market_cap (NULL 허용)

마지막 row 처리:
    - next_open / next_close / next_volume = NaN (float)
    - next_date = NaT (pandas.Timestamp NaT)
    - 015 정합: BacktestEngine이 마지막 봉의 next_* 매수 / exit_signal 매도 자동 skip.

look-ahead 차단:
    - next_*는 단순 shift(-1) — 다음 row의 가격 자체를 보지만,
      BacktestEngine은 이 값을 "다음 거래일에 체결할 가격"으로만 사용 (신호 조건 평가에는 사용 안 함).
    - PriceLoader는 신호 평가용 indicator를 만들지 않음 — 그건 conditions/* 책임.

결손 정책 (14.10):
    - PriceLoader는 결손 봉에 forward-fill을 하지 않음.
    - daily_prices에 row가 없으면 DataFrame에도 row 없음.
    - 호출자(또는 BacktestEngine)가 trading_calendar와 대조해 결손을 별도 보고할 책임.

결정론 (CLAUDE.md #8):
    - 항상 date ASC 정렬.
"""

from __future__ import annotations

from datetime import date as date_type

import pandas as pd
from sqlalchemy.orm import Session

from app.market_data import repositories

# BacktestEngine이 보는 컬럼 명세 (외부 사용자에게 노출).
PRICE_LOADER_BASE_COLUMNS: tuple[str, ...] = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_open",
    "adj_high",
    "adj_low",
    "adj_close",
    "adj_volume",
    "market_cap",
)
PRICE_LOADER_NEXT_COLUMNS: tuple[str, ...] = (
    "next_open",
    "next_close",
    "next_volume",
    "next_date",
    "adj_next_open",
    "adj_next_close",
)
PRICE_LOADER_COLUMNS: tuple[str, ...] = (
    *PRICE_LOADER_BASE_COLUMNS,
    *PRICE_LOADER_NEXT_COLUMNS,
)


class PriceLoader:
    """daily_prices → BacktestEngine 입력 DataFrame 변환.

    Args:
        session: SQLAlchemy Session (read-only 사용).

    사용 예시:
        loader = PriceLoader(session)
        df = loader.load("005930", date(2024, 1, 1), date(2024, 12, 31))
        # df는 BacktestEngine.run(df)에 그대로 전달 가능
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def load(
        self,
        symbol: str,
        start_date: date_type,
        end_date: date_type,
    ) -> pd.DataFrame:
        """단일 종목 일봉을 BacktestEngine 입력 DataFrame으로 반환.

        Args:
            symbol: 종목 코드.
            start_date / end_date: 포함 (inclusive).

        Returns:
            DataFrame — `PRICE_LOADER_COLUMNS` 순서로 컬럼이 들어 있고
            date ASC로 정렬되어 있다. 데이터가 없으면 빈 DataFrame (컬럼 명세는 동일).

            마지막 row의 next_open / next_close / next_volume = NaN,
            next_date = NaT (015 정합 — BacktestEngine이 자동 skip).

        Raises:
            없음. 빈 결과는 빈 DataFrame으로 반환 (호출자가 처리).
        """
        rows = repositories.get_price_range(
            self.session,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

        if not rows:
            return self._empty_dataframe()

        records: list[dict] = []
        for row in rows:
            records.append(
                {
                    "date": row.date,
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "volume": float(row.volume),
                    "adj_open": float(row.adj_open),
                    "adj_high": float(row.adj_high),
                    "adj_low": float(row.adj_low),
                    "adj_close": float(row.adj_close),
                    "adj_volume": float(row.adj_volume),
                    "market_cap": (
                        float(row.market_cap)
                        if row.market_cap is not None
                        else None
                    ),
                }
            )

        df = pd.DataFrame.from_records(records)
        # 결정론: repositories.get_price_range가 이미 date ASC지만 한 번 더 명시 정렬.
        df = df.sort_values("date").reset_index(drop=True)

        # next_* 채움 (015 정합 — 마지막 row는 NaN/NaT)
        df = self._attach_next_columns(df)

        # 컬럼 순서 정규화 (테스트 안정성)
        return df[list(PRICE_LOADER_COLUMNS)]

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _attach_next_columns(df: pd.DataFrame) -> pd.DataFrame:
        """next_open / next_close / next_volume / next_date / adj_next_* 채움.

        모두 단순 shift(-1) — 다음 거래일의 가격을 그대로 가져옴.
        15 정합: 마지막 row는 NaN/NaT — BacktestEngine이 자동 skip.

        ExecutionModel.get_entry_price(use_adjusted_price=True)가 `adj_next_open`
        컬럼을 찾을 수 있으므로 동일 값을 추가 컬럼으로도 노출 (호환성).
        """
        df = df.copy()
        df["next_open"] = df["adj_open"].shift(-1)
        df["next_close"] = df["adj_close"].shift(-1)
        df["next_volume"] = df["adj_volume"].shift(-1)
        # next_date는 date 컬럼을 그대로 1칸 shift — pandas는 마지막을 NaT로 채움
        df["next_date"] = df["date"].shift(-1)
        # ExecutionModel.get_entry_price 호환 (use_adjusted_price=True 분기)
        df["adj_next_open"] = df["next_open"]
        df["adj_next_close"] = df["next_close"]
        return df

    @staticmethod
    def _empty_dataframe() -> pd.DataFrame:
        """빈 결과 — 컬럼 명세는 동일하게 유지 (호출자 안정성)."""
        df = pd.DataFrame({col: pd.Series(dtype="object") for col in PRICE_LOADER_COLUMNS})
        return df


__all__ = ["PriceLoader", "PRICE_LOADER_COLUMNS", "PRICE_LOADER_BASE_COLUMNS", "PRICE_LOADER_NEXT_COLUMNS"]
