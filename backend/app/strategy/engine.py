"""StrategyEngine — 전략 JSON을 시장 데이터에 적용해 신호 생성.

설계서 03번 9절 + 02번 5절 (exit_signal vs exit_position 분리) 기반.

처리 범위:
    - entry         (시계열 매수 신호)
    - exit_signal   (시계열 매도 신호; 포지션 정보 불필요)
    - filters       (시장 환경 필터)

처리하지 않는 범위:
    - exit_position (take_profit/stop_loss/max_holding_days 등)
      → BacktestEngine + Portfolio가 매일 보유 종목마다 평가
    - position_sizing / cash_management / risk_management / execution
      → 각 전담 모듈이 처리
"""

from __future__ import annotations

import pandas as pd

from app.strategy.registry import condition_registry


class StrategyEngine:
    """전략 JSON을 시계열 신호로 변환.

    스레드 안전 (인스턴스 상태는 strategy dict 참조만).
    """

    def __init__(self, strategy_json: dict):
        self.strategy = strategy_json

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """df에 entry_signal / exit_signal / filter_signal / final_entry_signal 컬럼 추가."""
        df = df.copy()

        entry_section = self.strategy.get("entry")
        exit_signal_section = self.strategy.get("exit_signal")
        filters_section = self.strategy.get("filters")

        df["entry_signal"] = self._build_section_signal(df, entry_section)

        if exit_signal_section:
            df["exit_signal"] = self._build_section_signal(df, exit_signal_section)
        else:
            df["exit_signal"] = pd.Series(False, index=df.index)

        if filters_section:
            df["filter_signal"] = self._build_section_signal(df, filters_section)
        else:
            df["filter_signal"] = pd.Series(True, index=df.index)

        df["final_entry_signal"] = df["entry_signal"] & df["filter_signal"]

        return df

    # === 내부 헬퍼 ===

    def _build_section_signal(self, df: pd.DataFrame, section: dict | None) -> pd.Series:
        """한 섹션(entry / exit_signal / filters)의 신호 시리즈를 만든다.

        section=None 또는 conditions 빈 경우 → 모두 True (entry/filters 기본 가정).
        exit_signal 섹션이 없는 경우는 호출자가 별도로 False 시리즈를 만든다 (위 generate_signals).
        """
        if section is None:
            return pd.Series(True, index=df.index)

        logic = section.get("logic", "AND")

        if logic == "GROUP":
            return self._build_group_signal(df, section)

        conditions = section.get("conditions", [])
        if not conditions:
            return pd.Series(True, index=df.index)

        signals = [
            condition_registry.evaluate(c["type"], df, c)
            for c in conditions
        ]

        if logic == "AND":
            result = signals[0]
            for sig in signals[1:]:
                result = result & sig
            return result

        if logic == "OR":
            result = signals[0]
            for sig in signals[1:]:
                result = result | sig
            return result

        raise ValueError(f"지원하지 않는 logic입니다: {logic!r} (허용: 'AND', 'OR', 'GROUP')")

    def _build_group_signal(self, df: pd.DataFrame, section: dict) -> pd.Series:
        """GROUP logic — (그룹1) operator (그룹2) ... 형태.

        02번 4절: GROUP은 1단계 중첩만 지원. 그룹 안에 그룹을 두지 않는다.
        각 그룹은 일반 section 구조 (logic + conditions).
        """
        operator = section.get("operator", "OR")
        groups = section.get("groups", [])

        if not groups:
            return pd.Series(True, index=df.index)

        group_signals = [self._build_section_signal(df, group) for group in groups]
        result = group_signals[0]

        if operator == "OR":
            for sig in group_signals[1:]:
                result = result | sig
        elif operator == "AND":
            for sig in group_signals[1:]:
                result = result & sig
        else:
            raise ValueError(
                f"지원하지 않는 GROUP operator입니다: {operator!r} (허용: 'AND', 'OR')"
            )

        return result
