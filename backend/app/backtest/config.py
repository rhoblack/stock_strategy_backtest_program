"""백테스트 실행 설정.

Phase 1 단일 종목 한정. universe / priority / cash_management는 후속 단계.

Phase 10 step 021 — priority 알고리즘 + random_seed 실사용 (04-k / 13-n / 13-o).
priority_method / priority_tie_breaker / random_seed 필드 추가. 기존 호출자는
default 값 ("none" / "symbol_asc" / None)이 020 동작과 동일해 영향 없음.

Phase 10 step 022 — 포지션/매수 한도 (04-l + 04-m).
max_positions / max_daily_entries / daily_buy_budget 필드 추가. 모두
default=None → 020·021 동작 그대로 → Phase 1 골든 fixture 9지표 frozen 보존.
한도 적용은 priority 정렬 후 BacktestEngine._apply_position_limits가 담당.
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

    def __post_init__(self) -> None:
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
