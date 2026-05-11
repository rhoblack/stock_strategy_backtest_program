"""HistoricalBackfillJob — 과거 N일 일괄 수집 + 체크포인트 + rate-limit (14번 §6.1).

초기 데이터 구축 또는 결손 재수집용.
2,800 종목 × 10년치를 수집하는 장기 작업이므로 다음 두 메커니즘이 필수다:

    1. **체크포인트 저장** (data/backfill_checkpoint.json)
       - 단계(stage) 완료 상태 + 마지막 처리 종목 기록
       - 재시작 시 완료된 단계는 건너뜀 → 처음부터 재수집 불필요

    2. **RateLimiter** (utils.rate_limiter)
       - 요청 간 최소 0.5초 대기 (14.6.4)
       - 연속 실패 N회 → 30분 자동 일시정지
       - PykrxCollector retry(1s→5s→30s)와 계층 구분:
         * retry: 단일 요청 실패 시 재시도
         * RateLimiter: 요청 *간격* 제어 + 장기 차단 감지

설계 결정:

    1. **7단계 순서** (14.6.1)
       symbols → calendar → corporate_actions → daily_prices →
       adjusted_prices → market_cap → validate

       - symbols / calendar / corporate_actions 는 단계 통째로 1회
       - daily_prices 는 종목별 루프 (rate-limit 가장 높음)
       - adjusted_prices 는 daily_prices 완료 후 AdjustedPriceProcessor 호출
       - market_cap 는 symbols 정보(상장주식수)로 계산 — 본 step에서는 daily_prices의
         market_cap 필드를 신뢰(pykrx가 채워 줌), 별도 집계 없음
       - validate 는 MissingDataCheckJob 재사용

    2. **체크포인트 파일 경로 주입**
       - 기본: `data/backfill_checkpoint.json` (pathlib.Path)
       - 테스트: tmp_path fixture로 오버라이드 → 실제 파일 I/O 없음

    3. **결정론** (CLAUDE.md #8 / 13.12)
       - 종목 루프는 symbol ASC 정렬
       - 체크포인트 파일은 JSON sort_keys=True

    4. **corporate_actions 수집**
       - 현재 BaseCollector는 collect_corporate_actions 미지원
         (025 주석 "027~ 후속 step에서 별도 메서드 추가 예정")
       - 본 step에서는 corporate_actions 단계를 no-op(경고 1건) 처리
       - 실제 수집은 collector에 collect_corporate_actions가 추가된 뒤 활성화

    5. **market_cap 단계**
       - pykrx가 collect_daily_prices에서 market_cap을 이미 채워 줌
       - 별도 집계 없이 daily_prices에서 market_cap 컬럼을 그대로 저장
       - 본 단계는 "market_cap 집계 완료" 체크포인트만 표기 (no-op)

14번 정책 매핑:
    - §6.1 (초기 백필 7단계) — 본 잡 자체
    - §6.3 (재시도) — collector 위임 (PykrxCollector)
    - §6.4 (KRX 차단 대응) — RateLimiter 적용
    - §10 (생존편향) — symbols 수집 시 delisting 종목 포함 보존
    - §13 (결손 알림) — validate 단계에서 MissingDataCheckJob 재사용
    - §15 (look-ahead) — as_of_date 기준 이후 corporate_actions 무시

DailyUpdateJob과의 차이:
    - 단일 일자 vs 구간 (start, end)
    - 체크포인트 + rate-limit 없음 vs 있음
    - 7단계 순서적 실행
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_type
from pathlib import Path
from typing import TYPE_CHECKING

from app.data_pipeline.jobs.base import BaseJob, JobResult
from app.data_pipeline.jobs.missing_data_check import (
    MissingDataCheckConfig,
    MissingDataCheckJob,
)
from app.data_pipeline.processors.adjusted_price import (
    AdjustedPriceInput,
    AdjustedPriceProcessor,
    CorporateActionEvent,
)
from app.data_pipeline.utils.rate_limiter import RateLimiter
from app.market_data import repositories

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from app.data_pipeline.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

JOB_NAME = "historical_backfill"

# 7단계 순서 (체크포인트 completed_stages 키값으로 사용)
STAGE_SYMBOLS = "symbols"
STAGE_CALENDAR = "calendar"
STAGE_CORPORATE_ACTIONS = "corporate_actions"
STAGE_DAILY_PRICES = "daily_prices"
STAGE_ADJUSTED_PRICES = "adjusted_prices"
STAGE_MARKET_CAP = "market_cap"
STAGE_VALIDATE = "validate"

ALL_STAGES: tuple[str, ...] = (
    STAGE_SYMBOLS,
    STAGE_CALENDAR,
    STAGE_CORPORATE_ACTIONS,
    STAGE_DAILY_PRICES,
    STAGE_ADJUSTED_PRICES,
    STAGE_MARKET_CAP,
    STAGE_VALIDATE,
)

# 체크포인트 기본 경로 (프로젝트 루트의 data/ 디렉토리)
_DEFAULT_CHECKPOINT_PATH = Path("data") / "backfill_checkpoint.json"


# ---------------------------------------------------------------------------
# 체크포인트 dataclass
# ---------------------------------------------------------------------------


@dataclass
class BackfillCheckpoint:
    """HistoricalBackfillJob 진행 상황 체크포인트.

    Attributes:
        as_of_date: 백필 기준 end_date (ISO 문자열).
        completed_stages: 완료된 단계 이름 리스트 (ALL_STAGES 순서와 일치).
        last_symbol: daily_prices 단계에서 마지막으로 완료한 종목코드.
            None이면 daily_prices를 아직 시작하지 않았거나 완료된 상태.
    """

    as_of_date: str
    completed_stages: list[str]
    last_symbol: str | None = None

    @classmethod
    def load(cls, path: Path) -> BackfillCheckpoint | None:
        """파일에서 체크포인트를 로드.

        파일이 없거나 파싱 실패 시 None 반환 (신규 시작으로 처리).
        """
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(
                as_of_date=data["as_of_date"],
                completed_stages=data.get("completed_stages", []),
                last_symbol=data.get("last_symbol"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("체크포인트 로드 실패 (신규 시작): %s", exc)
            return None

    def save(self, path: Path) -> None:
        """체크포인트를 JSON 파일로 저장.

        디렉토리가 없으면 자동 생성.
        결정론: sort_keys=True.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "as_of_date": self.as_of_date,
                    "completed_stages": self.completed_stages,
                    "last_symbol": self.last_symbol,
                },
                f,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

    def is_stage_done(self, stage: str) -> bool:
        """단계가 이미 완료됐는지 확인."""
        return stage in self.completed_stages

    def mark_stage_done(self, stage: str, path: Path) -> None:
        """단계 완료 표시 후 즉시 저장 (중단 안전성)."""
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.save(path)

    def update_last_symbol(self, symbol: str, path: Path) -> None:
        """종목별 완료 후 last_symbol 갱신 → 즉시 저장."""
        self.last_symbol = symbol
        self.save(path)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalBackfillConfig:
    """HistoricalBackfillJob 설정.

    Attributes:
        start_date / end_date: 수집 구간 (포함).
        markets: 캘린더 수집 대상.
        symbols: 일봉 수집 대상. None이면 collect_symbols 결과 전부.
        apply_adjusted_price: corporate_actions 기반 수정주가 재계산 여부.
        checkpoint_path: 체크포인트 파일 경로 (기본 data/backfill_checkpoint.json).
        validate_markets: validate 단계에서 결손 검사할 시장 목록. None이면 markets와 동일.
        rate_limiter: 요청 간격 제어 객체. None이면 기본 RateLimiter() 사용.
    """

    start_date: date_type
    end_date: date_type
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    symbols: tuple[str, ...] | None = None
    apply_adjusted_price: bool = True
    checkpoint_path: Path = _DEFAULT_CHECKPOINT_PATH
    validate_markets: tuple[str, ...] | None = None
    rate_limiter: RateLimiter | None = None

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date > end_date: "
                f"{self.start_date.isoformat()} > {self.end_date.isoformat()}"
            )


# ---------------------------------------------------------------------------
# HistoricalBackfillJob
# ---------------------------------------------------------------------------


class HistoricalBackfillJob(BaseJob):
    """과거 N일 일괄 수집 잡 — 체크포인트 + rate-limit 포함 (14번 §6.1).

    사용 예:
        job = HistoricalBackfillJob(
            config=HistoricalBackfillConfig(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 12, 31),
            ),
            collector=PykrxCollector(),
            session_factory=SessionLocal,
        )
        result = job.run()

    재시작 시:
        - checkpoint_path가 존재하면 완료된 단계를 건너뜀
        - last_symbol이 있으면 daily_prices 단계에서 해당 종목 이후부터 이어받음
        - as_of_date가 다르면 새 백필로 간주 (체크포인트 무시)

    Args:
        config: HistoricalBackfillConfig (frozen dataclass).
        collector: BaseCollector 구현체 (pykrx / mock).
        session_factory: 새 Session callable.
        processor: AdjustedPriceProcessor (None이면 기본 인스턴스).
        name: 잡 식별자.
        schedule: None (백필은 수동 실행 전용).
        clock: UTC 시각 callable (테스트에서 고정값 주입 가능).
    """

    def __init__(
        self,
        config: HistoricalBackfillConfig,
        collector: BaseCollector,
        session_factory: Callable[[], Session],
        *,
        processor: AdjustedPriceProcessor | None = None,
        name: str = JOB_NAME,
        schedule: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(name, schedule=schedule)
        self._config = config
        self._collector = collector
        self._session_factory = session_factory
        self._processor = processor or AdjustedPriceProcessor()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._rate_limiter: RateLimiter = config.rate_limiter or RateLimiter()

    # ------------------------------------------------------------------
    # run() 진입점 — 7단계 순서 실행
    # ------------------------------------------------------------------

    def run(self) -> JobResult:
        """7단계 순서 실행 (체크포인트 이어받기 포함).

        완료된 단계는 스킵. 각 단계 완료 후 체크포인트 즉시 저장.

        Returns:
            JobResult — 전체 성공/실패 + 단계별 통계.
        """
        started_at = self._clock()
        warnings: list[str] = []
        errors: list[str] = []
        stats: dict[str, int] = {
            "symbols_upserted": 0,
            "trading_days_upserted": 0,
            "corporate_actions_collected": 0,
            "daily_prices_upserted": 0,
            "events_applied": 0,
            "events_skipped": 0,
            "markets": len(self._config.markets),
            "days_span": (self._config.end_date - self._config.start_date).days + 1,
            "symbols_processed": 0,
            "missing_count": 0,
        }
        success = True

        # 체크포인트 로드 (없으면 신규 시작)
        checkpoint = self._load_or_create_checkpoint()

        try:
            # ----------------------------------------------------------------
            # Stage 1: symbols
            # ----------------------------------------------------------------
            symbols_data = None
            if not checkpoint.is_stage_done(STAGE_SYMBOLS):
                self._rate_limiter.wait()
                try:
                    symbols_data = self._collector.collect_symbols(self._config.end_date)
                    self._rate_limiter.record_success()
                    warnings.extend(symbols_data.warnings)
                    with self._session_scope() as session:
                        for row in symbols_data.rows:
                            repositories.upsert_symbol(
                                session,
                                {
                                    "symbol": row.symbol,
                                    "name": row.name,
                                    "market": row.market,
                                    "listing_date": row.listing_date,
                                    "delisting_date": row.delisting_date,
                                    "sector": row.sector,
                                    "is_etf": row.is_etf,
                                    "is_etn": row.is_etn,
                                    "is_spac": row.is_spac,
                                    "is_preferred": row.is_preferred,
                                    "is_managed": row.is_managed,
                                    "is_halted": row.is_halted,
                                },
                            )
                        stats["symbols_upserted"] = len(symbols_data.rows)
                        session.commit()
                    logger.info(
                        "[%s] 1/7 symbols 완료: %d건",
                        self.name,
                        stats["symbols_upserted"],
                    )
                    checkpoint.mark_stage_done(STAGE_SYMBOLS, self._config.checkpoint_path)
                except Exception as exc:  # noqa: BLE001
                    self._rate_limiter.record_failure()
                    raise RuntimeError(f"symbols 단계 실패: {exc}") from exc
            else:
                logger.info("[%s] 1/7 symbols 이미 완료 — 스킵", self.name)

            # ----------------------------------------------------------------
            # Stage 2: calendar
            # ----------------------------------------------------------------
            if not checkpoint.is_stage_done(STAGE_CALENDAR):
                with self._session_scope() as session:
                    for market in self._config.markets:
                        self._rate_limiter.wait()
                        try:
                            cal_data = self._collector.collect_trading_calendar(
                                self._config.start_date,
                                self._config.end_date,
                                market,
                            )
                            self._rate_limiter.record_success()
                            warnings.extend(cal_data.warnings)
                            for crow in cal_data.rows:
                                repositories.upsert_trading_day(
                                    session,
                                    date=crow.date,
                                    market=crow.market,
                                    is_trading_day=crow.is_trading_day,
                                    holiday_name=crow.holiday_name,
                                )
                            stats["trading_days_upserted"] += len(cal_data.rows)
                        except Exception as exc:  # noqa: BLE001
                            self._rate_limiter.record_failure()
                            raise RuntimeError(f"calendar 단계 실패 (market={market}): {exc}") from exc
                    session.commit()
                logger.info(
                    "[%s] 2/7 calendar 완료: %d건",
                    self.name,
                    stats["trading_days_upserted"],
                )
                checkpoint.mark_stage_done(STAGE_CALENDAR, self._config.checkpoint_path)
            else:
                logger.info("[%s] 2/7 calendar 이미 완료 — 스킵", self.name)

            # ----------------------------------------------------------------
            # Stage 3: corporate_actions
            # ----------------------------------------------------------------
            if not checkpoint.is_stage_done(STAGE_CORPORATE_ACTIONS):
                # BaseCollector에 collect_corporate_actions 미지원 (025 주석 참조)
                # 027 이후 collector에 메서드가 추가되면 실제 수집으로 교체
                warnings.append(
                    "corporate_actions 단계: collector.collect_corporate_actions 미지원 "
                    "(028 §3 — 028 이후 정밀화). 기존 DB 데이터 재사용."
                )
                logger.info("[%s] 3/7 corporate_actions — no-op (미지원)", self.name)
                checkpoint.mark_stage_done(
                    STAGE_CORPORATE_ACTIONS, self._config.checkpoint_path
                )
            else:
                logger.info("[%s] 3/7 corporate_actions 이미 완료 — 스킵", self.name)

            # ----------------------------------------------------------------
            # Stage 4: daily_prices (종목별 루프, rate-limit 적용)
            # ----------------------------------------------------------------
            if not checkpoint.is_stage_done(STAGE_DAILY_PRICES):
                # 대상 종목 결정
                if self._config.symbols is not None:
                    target_symbols: tuple[str, ...] = tuple(
                        sorted(self._config.symbols)
                    )
                elif symbols_data is not None:
                    target_symbols = tuple(
                        sorted(r.symbol for r in symbols_data.rows)
                    )
                else:
                    # symbols 단계가 이미 완료(스킵)된 경우 — DB에서 조회
                    with self._session_scope() as session:
                        active = repositories.list_symbols(session)
                    target_symbols = tuple(sorted(s.symbol for s in active))

                # last_symbol 이어받기 처리
                resume_symbol = checkpoint.last_symbol
                resume_idx = 0
                if resume_symbol is not None and resume_symbol in target_symbols:
                    resume_idx = list(target_symbols).index(resume_symbol) + 1
                    logger.info(
                        "[%s] 4/7 daily_prices 이어받기: %s 이후 (%d/%d)",
                        self.name,
                        resume_symbol,
                        resume_idx,
                        len(target_symbols),
                    )

                remaining_symbols = target_symbols[resume_idx:]
                total = len(target_symbols)
                done = resume_idx

                for symbol in remaining_symbols:
                    self._rate_limiter.wait()
                    try:
                        prices_data = self._collector.collect_daily_prices(
                            (symbol,),
                            self._config.start_date,
                            self._config.end_date,
                        )
                        self._rate_limiter.record_success()
                        warnings.extend(prices_data.warnings)

                        with self._session_scope() as session:
                            upserted = repositories.bulk_upsert_daily_prices(
                                session,
                                rows=[
                                    {
                                        "symbol": r.symbol,
                                        "date": r.date,
                                        "open": r.open,
                                        "high": r.high,
                                        "low": r.low,
                                        "close": r.close,
                                        "volume": r.volume,
                                        "adj_open": r.adj_open,
                                        "adj_high": r.adj_high,
                                        "adj_low": r.adj_low,
                                        "adj_close": r.adj_close,
                                        "adj_volume": r.adj_volume,
                                        "market_cap": r.market_cap,
                                    }
                                    for r in prices_data.rows
                                ],
                            )
                            session.commit()
                        stats["daily_prices_upserted"] += upserted
                        done += 1
                        stats["symbols_processed"] = done
                    except Exception as exc:  # noqa: BLE001
                        self._rate_limiter.record_failure()
                        warnings.append(f"daily_prices 수집 실패 ({symbol}): {exc}")
                        # 단일 종목 실패는 경고로만 처리 → 다음 종목으로 계속
                    finally:
                        # 종목 완료(성공 또는 실패) 후 last_symbol 갱신
                        checkpoint.update_last_symbol(
                            symbol, self._config.checkpoint_path
                        )

                    if done % 100 == 0:
                        logger.info(
                            "[%s] 4/7 daily_prices 진행: %d/%d",
                            self.name,
                            done,
                            total,
                        )

                logger.info(
                    "[%s] 4/7 daily_prices 완료: %d건 적재",
                    self.name,
                    stats["daily_prices_upserted"],
                )
                # last_symbol 초기화 (다음 재시작 시 daily_prices 완료로 스킵)
                checkpoint.last_symbol = None
                checkpoint.mark_stage_done(STAGE_DAILY_PRICES, self._config.checkpoint_path)
            else:
                logger.info("[%s] 4/7 daily_prices 이미 완료 — 스킵", self.name)

            # ----------------------------------------------------------------
            # Stage 5: adjusted_prices
            # ----------------------------------------------------------------
            if not checkpoint.is_stage_done(STAGE_ADJUSTED_PRICES):
                if self._config.apply_adjusted_price:
                    events = self._collect_corporate_actions_from_db(
                        self._config.symbols, self._config.end_date
                    )
                    if events:
                        # daily_prices를 DB에서 재로드해 processor에 투입
                        from app.data_pipeline.collectors.base import (
                            RawDailyPriceRow,
                            RawDailyPricesData,
                        )

                        with self._session_scope() as session:
                            target = (
                                self._config.symbols
                                or tuple(
                                    s.symbol for s in repositories.list_symbols(session)
                                )
                            )
                            price_rows_db = []
                            for sym in sorted(target):
                                db_rows = repositories.get_price_range(
                                    session,
                                    symbol=sym,
                                    start_date=self._config.start_date,
                                    end_date=self._config.end_date,
                                )
                                price_rows_db.extend(
                                    RawDailyPriceRow(
                                        symbol=r.symbol,
                                        date=r.date,
                                        open=float(r.open or 0),
                                        high=float(r.high or 0),
                                        low=float(r.low or 0),
                                        close=float(r.close or 0),
                                        volume=float(r.volume or 0),
                                        adj_open=float(r.adj_open or 0),
                                        adj_high=float(r.adj_high or 0),
                                        adj_low=float(r.adj_low or 0),
                                        adj_close=float(r.adj_close or 0),
                                        adj_volume=float(r.adj_volume or 0),
                                        market_cap=float(r.market_cap) if r.market_cap is not None else None,
                                    )
                                    for r in db_rows
                                )

                        raw_prices = RawDailyPricesData(
                            rows=tuple(
                                sorted(price_rows_db, key=lambda r: (r.symbol, r.date))
                            ),
                            start_date=self._config.start_date,
                            end_date=self._config.end_date,
                            source="db_reload",
                        )
                        proc_result = self._processor.process(
                            AdjustedPriceInput(
                                prices=raw_prices,
                                corporate_actions=events,
                                as_of_date=self._config.end_date,
                            )
                        )
                        warnings.extend(proc_result.warnings)
                        for issue in proc_result.validation.issues:
                            warnings.append(
                                f"adjusted_price {issue.severity}: "
                                f"{issue.code} — {issue.message}"
                            )
                        for k, v in proc_result.stats:
                            if k == "events_applied":
                                stats["events_applied"] = v
                            elif k.startswith("events_skipped"):
                                stats["events_skipped"] += v

                        # 재계산된 adj_* 를 DB에 반영
                        with self._session_scope() as session:
                            repositories.bulk_upsert_daily_prices(
                                session,
                                rows=[
                                    {
                                        "symbol": r.symbol,
                                        "date": r.date,
                                        "open": r.open,
                                        "high": r.high,
                                        "low": r.low,
                                        "close": r.close,
                                        "volume": r.volume,
                                        "adj_open": r.adj_open,
                                        "adj_high": r.adj_high,
                                        "adj_low": r.adj_low,
                                        "adj_close": r.adj_close,
                                        "adj_volume": r.adj_volume,
                                        "market_cap": r.market_cap,
                                    }
                                    for r in proc_result.output
                                ],
                            )
                            session.commit()
                    else:
                        warnings.append(
                            "adjusted_prices 단계: corporate_actions 0건 — 수정주가 재계산 없음."
                        )
                else:
                    warnings.append("adjusted_prices 단계: apply_adjusted_price=False — 스킵.")

                logger.info("[%s] 5/7 adjusted_prices 완료", self.name)
                checkpoint.mark_stage_done(
                    STAGE_ADJUSTED_PRICES, self._config.checkpoint_path
                )
            else:
                logger.info("[%s] 5/7 adjusted_prices 이미 완료 — 스킵", self.name)

            # ----------------------------------------------------------------
            # Stage 6: market_cap
            # ----------------------------------------------------------------
            if not checkpoint.is_stage_done(STAGE_MARKET_CAP):
                # pykrx가 collect_daily_prices에서 market_cap을 이미 채워 줌
                # 별도 집계 없이 단계 완료 표기만
                warnings.append(
                    "market_cap 단계: pykrx 일봉에 포함된 market_cap 필드를 그대로 사용. "
                    "별도 집계 없음 (14.6.1 §6)."
                )
                logger.info("[%s] 6/7 market_cap 완료 (no-op)", self.name)
                checkpoint.mark_stage_done(STAGE_MARKET_CAP, self._config.checkpoint_path)
            else:
                logger.info("[%s] 6/7 market_cap 이미 완료 — 스킵", self.name)

            # ----------------------------------------------------------------
            # Stage 7: validate
            # ----------------------------------------------------------------
            if not checkpoint.is_stage_done(STAGE_VALIDATE):
                validate_markets = (
                    self._config.validate_markets or self._config.markets
                )
                total_missing = 0
                for market in validate_markets:
                    check_job = MissingDataCheckJob(
                        config=MissingDataCheckConfig(
                            start_date=self._config.start_date,
                            end_date=self._config.end_date,
                            market=market,
                            symbols=self._config.symbols,
                        ),
                        session_factory=self._session_factory,
                        schedule=None,
                        clock=self._clock,
                    )
                    check_result = check_job.run()
                    warnings.extend(check_result.warnings)
                    total_missing += check_job.last_alert.missing_count

                stats["missing_count"] = total_missing
                logger.info(
                    "[%s] 7/7 validate 완료: missing %d건",
                    self.name,
                    total_missing,
                )
                checkpoint.mark_stage_done(STAGE_VALIDATE, self._config.checkpoint_path)
            else:
                logger.info("[%s] 7/7 validate 이미 완료 — 스킵", self.name)

        except Exception as exc:  # noqa: BLE001
            success = False
            errors.append(f"{type(exc).__name__}: {exc}")

        finished_at = self._clock()
        return JobResult(
            job_name=self.name,
            success=success,
            started_at=started_at,
            finished_at=finished_at,
            stats=tuple(
                sorted(((k, int(v)) for k, v in stats.items()), key=lambda kv: kv[0])
            ),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _load_or_create_checkpoint(self) -> BackfillCheckpoint:
        """체크포인트 로드 또는 신규 생성.

        as_of_date가 다르면 새 백필로 간주 — 기존 체크포인트 무시.
        """
        existing = BackfillCheckpoint.load(self._config.checkpoint_path)
        if existing is not None and existing.as_of_date == self._config.end_date.isoformat():
            logger.info(
                "[%s] 체크포인트 로드: 완료 단계=%s / last_symbol=%s",
                self.name,
                existing.completed_stages,
                existing.last_symbol,
            )
            return existing

        if existing is not None:
            logger.info(
                "[%s] as_of_date 변경 (%s → %s) — 신규 체크포인트 시작",
                self.name,
                existing.as_of_date,
                self._config.end_date.isoformat(),
            )

        return BackfillCheckpoint(
            as_of_date=self._config.end_date.isoformat(),
            completed_stages=[],
            last_symbol=None,
        )

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def _collect_corporate_actions_from_db(
        self,
        symbols: tuple[str, ...] | None,
        as_of_date: date_type,
    ) -> tuple[CorporateActionEvent, ...]:
        """DB에서 corporate_actions를 로드해 CorporateActionEvent tuple로 반환.

        14.15 look-ahead 차단: as_of_date 이후 이벤트는 processor가 자동 무시.
        """
        events: list[CorporateActionEvent] = []
        with self._session_scope() as session:
            if symbols is not None:
                target = tuple(sorted(symbols))
            else:
                active = repositories.list_symbols(session)
                target = tuple(sorted(s.symbol for s in active))

            for symbol in target:
                rows = repositories.get_corporate_actions(
                    session, symbol, end_date=as_of_date
                )
                events.extend(
                    CorporateActionEvent(
                        symbol=ca.symbol,
                        event_date=ca.event_date,
                        event_type=ca.event_type,
                        ratio=ca.ratio,
                        dividend_amount=ca.dividend_amount,
                    )
                    for ca in rows
                )
        return tuple(events)


__all__ = [
    "ALL_STAGES",
    "BackfillCheckpoint",
    "HistoricalBackfillConfig",
    "HistoricalBackfillJob",
    "JOB_NAME",
    "STAGE_ADJUSTED_PRICES",
    "STAGE_CALENDAR",
    "STAGE_CORPORATE_ACTIONS",
    "STAGE_DAILY_PRICES",
    "STAGE_MARKET_CAP",
    "STAGE_SYMBOLS",
    "STAGE_VALIDATE",
]
