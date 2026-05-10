"""백테스트 실행 설정.

Phase 1 단일 종목 한정. universe / priority / cash_management는 후속 단계.

Phase 10 step 021 — priority 알고리즘 + random_seed 실사용 (04-k / 13-n / 13-o).
priority_method / priority_tie_breaker / random_seed 필드 추가. 기존 호출자는
default 값 ("none" / "symbol_asc" / None)이 020 동작과 동일해 영향 없음.

Phase 10 step 022 — 포지션/매수 한도 (04-l + 04-m).
max_positions / max_daily_entries / daily_buy_budget 필드 추가. 모두
default=None → 020·021 동작 그대로 → Phase 1 골든 fixture 9지표 frozen 보존.
한도 적용은 priority 정렬 후 BacktestEngine._apply_position_limits가 담당.

Phase 10 step 023 — 상한가/하한가 차단 정책 (04-o + 13-q).
allow_buy_limit_up / allow_sell_limit_down / limit_pct 필드 추가. 모두 default
보수 (False / False / 0.27) — 단일 종목 골든 fixture에는 상한가/하한가
시나리오가 없어 9지표 frozen 보존. 상장폐지 강제 매도는 BacktestEngine.run의
delisting_dates 인자로 전달 (per-symbol 매핑이라 dataclass에 두기 부적절).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type

# 지원 priority method 화이트리스트 (정확성 정책 13.8.3 — 04번 §11).
# 본 step에서는 4종 도입. 13.8.3 명세의 volume_ratio_desc / price_change_desc /
# score_desc 등은 후속 step에서 추가하며, 미지원 값을 받으면 ValueError.
SUPPORTED_PRIORITY_METHODS: frozenset[str] = frozenset(
    {
        "none",                # 020 호환 — symbol ASC만
        "trading_value_desc",  # 13.8.3 — 후보의 today close × volume 내림차순
        "market_cap_desc",     # 13.8.3 — 후보의 today market_cap 내림차순
        "random",              # 13.8.3 — random.Random(seed) 셔플
    }
)

# 지원 tie-breaker 화이트리스트 (13.8.4). symbol_asc만 본 step에 도입.
# 정렬 키의 마지막 요소로 들어가 결정론을 보장한다.
SUPPORTED_PRIORITY_TIE_BREAKERS: frozenset[str] = frozenset({"symbol_asc"})


@dataclass(frozen=True)
class BacktestConfig:
    """단일/복수 종목 백테스트 설정."""

    symbol: str
    start_date: date_type
    end_date: date_type
    position_size_amount: float  # fixed_amount: 종목당 매수 금액
    initial_cash: float

    market: str = "KOSPI"
    entry_price_type: str = "next_open"
    exit_price_type: str = "next_open"
    max_gap_pct_for_entry: float = 5.0  # 정확성 정책 13.4.1
    skip_no_volume: bool = True  # 정확성 정책 13.4.4

    # === priority 알고리즘 (정확성 정책 13.8 + 04번 §11) ===
    # default "none" → 020 동작과 동일 (symbol ASC tie-breaker만).
    priority_method: str = "none"
    # 동순위 결정. 모든 method의 정렬 키 마지막 요소로 항상 적용 (CLAUDE.md #8).
    priority_tie_breaker: str = "symbol_asc"
    # 무작위 priority method 사용 시 결정론 보장용 시드 (정확성 정책 13.12.2).
    # priority_method="random"이면 None 금지 — __post_init__에서 ValueError.
    random_seed: int | None = None

    # === 포지션/매수 한도 (04-l + 04-m, 정확성 정책 13.8) ===
    # 모두 default=None → 020·021 동작과 동일 (한도 미적용).
    # priority가 정한 순서를 그대로 따라 한도 적용 — 결정론 (CLAUDE.md #8).
    #
    # max_positions: 동시 보유 종목 수 상한 (현재 보유 + 신규 매수 후보 합 기준).
    #   예) 보유=2 + max_positions=3 → 신규 매수는 1개까지만.
    # max_daily_entries: 하루 신규 매수 종목 수 상한 (보유와 무관, 후보 리스트 자체 자름).
    #   예) max_daily_entries=1 + 후보=3 → priority 1순위 후보만 매수 시도.
    # daily_buy_budget: 하루 매수 가능 총 금액 상한 (실 체결 cost 누적 — net_amount 기준).
    #   매수 루프 진행 중 cumulative + 새 비용 > budget이면 그 후보부터 skip.
    max_positions: int | None = None
    max_daily_entries: int | None = None
    daily_buy_budget: float | None = None

    # === PositionSizer (05번 §8) ===
    # default "fixed_amount" → 기존 position_size_amount 동작 그대로 (하위 호환).
    # "fixed_ratio"  : portfolio.total_equity() × sizing_ratio → 수량 계산.
    # "equal_weight" : portfolio.total_equity() / max_positions → 수량 계산.
    #                  max_positions(포지션 한도)와 동일 필드를 공유하므로,
    #                  equal_weight 사용 시 max_positions를 반드시 지정해야 한다.
    sizing_method: str = "fixed_amount"
    # fixed_ratio 방식 전용: 총자산 대비 비율 (예: 0.1 → 10%). (0, 1] 범위.
    # "fixed_amount" / "equal_weight" 방식에서는 무시한다.
    sizing_ratio: float | None = None

    # === 상한가/하한가 차단 (04-o + 정확성 정책 13.4.3 / 13-q) ===
    # KOSPI/KOSDAQ 가격 제한폭 ±30% 정책 (정확성 정책 13.4.3).
    # default 보수: 상한가 매수 / 하한가 매도 모두 차단 (skip + event_log).
    # 단일 종목 골든 fixture에는 상한가/하한가 시나리오 없음 → 9지표 frozen 보존.
    #
    # 판정 정책 (13.4.3):
    #   1. row에 `is_limit_up` / `is_limit_down` 컬럼이 있으면 그 값을 사용
    #      (PriceLoader가 14번 데이터 파이프라인에서 미리 채울 수 있는 자리).
    #   2. 컬럼이 없으면 fallback: high == low and pct_change >= limit_pct
    #      (보수적 임계 — KOSPI/KOSDAQ 한도 30%의 90% 정도인 0.27 default).
    #
    # allow_buy_limit_up=True로 두면 상한가에서도 매수 시도 (현실 비현실적이지만
    # 백테스트 옵션으로 허용). allow_sell_limit_down=True도 마찬가지로 매도 시도.
    allow_buy_limit_up: bool = False
    allow_sell_limit_down: bool = False
    # fallback 판정 임계 (소수). 0.27 = +27% 이상 상승 + high==low (단일 가격) →
    # 상한가로 간주. 0.295로 올리면 보다 엄격, 0.25로 내리면 보다 보수적.
    limit_pct: float = 0.27

    def __post_init__(self) -> None:
        # === sizing_method 검증 (05번 §8) ===
        SUPPORTED_SIZING_METHODS: frozenset[str] = frozenset(
            {"fixed_amount", "fixed_ratio", "equal_weight"}
        )
        if self.sizing_method not in SUPPORTED_SIZING_METHODS:
            raise ValueError(
                f"지원하지 않는 sizing_method: {self.sizing_method!r}. "
                f"허용 값: {sorted(SUPPORTED_SIZING_METHODS)}"
            )
        # fixed_ratio이면 sizing_ratio 필수
        if self.sizing_method == "fixed_ratio" and self.sizing_ratio is None:
            raise ValueError(
                "sizing_method='fixed_ratio'는 sizing_ratio가 필요합니다"
            )
        # sizing_ratio가 명시된 경우 (0, 1] 범위 강제
        if self.sizing_ratio is not None:
            if isinstance(self.sizing_ratio, bool) or not isinstance(
                self.sizing_ratio, (int, float)
            ):
                raise ValueError(
                    f"sizing_ratio는 숫자여야 합니다: "
                    f"{type(self.sizing_ratio).__name__}"
                )
            if not (0 < self.sizing_ratio <= 1):
                raise ValueError(
                    f"sizing_ratio는 (0, 1] 범위여야 합니다: {self.sizing_ratio}"
                )

        if self.priority_method not in SUPPORTED_PRIORITY_METHODS:
            raise ValueError(
                f"지원하지 않는 priority_method: {self.priority_method!r}. "
                f"허용 값: {sorted(SUPPORTED_PRIORITY_METHODS)}"
            )
        if self.priority_tie_breaker not in SUPPORTED_PRIORITY_TIE_BREAKERS:
            raise ValueError(
                f"지원하지 않는 priority_tie_breaker: {self.priority_tie_breaker!r}. "
                f"허용 값: {sorted(SUPPORTED_PRIORITY_TIE_BREAKERS)}"
            )
        # priority_method="random" + random_seed=None은 결정론을 깨므로 거부
        # (CLAUDE.md #8 / 정확성 정책 13.12.1). default seed=0 등의 implicit fallback은
        # "보이지 않는 결정론"이 되어 실수를 유발하므로 명시적 ValueError로 차단.
        if self.priority_method == "random" and self.random_seed is None:
            raise ValueError(
                "priority_method='random'은 random_seed가 필요합니다 "
                "(정확성 정책 13.12.2). int 시드를 명시하세요."
            )

        # === 한도 검증 (04-l + 04-m) ===
        # None은 "한도 미적용". 명시적으로 0/음수를 받으면 매수 자체가 불가하거나
        # 의미가 모호하므로 ValueError로 거부 (정책 명시 → "보이지 않는 차단" 방지).
        if self.max_positions is not None:
            if not isinstance(self.max_positions, int) or isinstance(
                self.max_positions, bool
            ):
                raise ValueError(
                    f"max_positions는 int여야 합니다: {type(self.max_positions).__name__}"
                )
            if self.max_positions <= 0:
                raise ValueError(
                    f"max_positions는 양수여야 합니다 (None이면 무제한): "
                    f"{self.max_positions}"
                )
        if self.max_daily_entries is not None:
            if not isinstance(self.max_daily_entries, int) or isinstance(
                self.max_daily_entries, bool
            ):
                raise ValueError(
                    f"max_daily_entries는 int여야 합니다: "
                    f"{type(self.max_daily_entries).__name__}"
                )
            if self.max_daily_entries <= 0:
                raise ValueError(
                    f"max_daily_entries는 양수여야 합니다 (None이면 무제한): "
                    f"{self.max_daily_entries}"
                )
        if self.daily_buy_budget is not None:
            if isinstance(self.daily_buy_budget, bool) or not isinstance(
                self.daily_buy_budget, (int, float)
            ):
                raise ValueError(
                    f"daily_buy_budget는 숫자여야 합니다: "
                    f"{type(self.daily_buy_budget).__name__}"
                )
            if self.daily_buy_budget <= 0:
                raise ValueError(
                    f"daily_buy_budget는 양수여야 합니다 (None이면 무제한): "
                    f"{self.daily_buy_budget}"
                )

        # === 상한가/하한가 (023) ===
        # bool 검증 — int 0/1을 받지 않도록 명시 (타입 안전 + 결정론).
        if not isinstance(self.allow_buy_limit_up, bool):
            raise ValueError(
                f"allow_buy_limit_up는 bool이어야 합니다: "
                f"{type(self.allow_buy_limit_up).__name__}"
            )
        if not isinstance(self.allow_sell_limit_down, bool):
            raise ValueError(
                f"allow_sell_limit_down는 bool이어야 합니다: "
                f"{type(self.allow_sell_limit_down).__name__}"
            )
        # limit_pct는 0~1 범위 양수. 0이면 모든 상승봉을 상한가로 오판하므로 거부.
        # 1 이상이면 상한가가 영원히 트리거되지 않으므로 의미 없음.
        if isinstance(self.limit_pct, bool) or not isinstance(
            self.limit_pct, (int, float)
        ):
            raise ValueError(
                f"limit_pct는 숫자여야 합니다: {type(self.limit_pct).__name__}"
            )
        if not (0 < self.limit_pct < 1):
            raise ValueError(
                f"limit_pct는 (0, 1) 범위 내여야 합니다 (KOSPI/KOSDAQ 한도 0.30): "
                f"{self.limit_pct}"
            )
