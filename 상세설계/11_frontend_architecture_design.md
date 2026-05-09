# 11. 프론트엔드 구조 및 컴포넌트 상세 설계서

## 1. 목적

프론트엔드는 사용자가 전략을 쉽게 만들고, 백테스트 결과를 직관적으로 이해하게 만드는 핵심 UI 계층입니다.

이 프로그램에서는 GUI 품질이 매우 중요합니다.

---

## 2. 기술 스택

추천:

```text
React
TypeScript
TanStack Query
TanStack Table
TradingView Lightweight Charts
ECharts 또는 Recharts
```

---

## 3. 전체 폴더 구조

```text
frontend/src/
├─ app/
│  ├─ App.tsx
│  ├─ router.tsx
│  └─ providers.tsx
│
├─ api/
│  ├─ client.ts
│  ├─ strategies.ts
│  ├─ backtests.ts
│  ├─ conditions.ts
│  └─ market.ts
│
├─ pages/
│  ├─ StrategyListPage.tsx
│  ├─ StrategyBuilderPage.tsx
│  ├─ BacktestRunPage.tsx
│  ├─ BacktestResultPage.tsx
│  └─ StrategyComparePage.tsx
│
├─ features/
│  ├─ strategy-builder/
│  ├─ backtest-result/
│  └─ universe-selector/
│
├─ components/
│  ├─ layout/
│  ├─ ui/
│  └─ charts/
│
├─ hooks/
├─ types/
└─ utils/
```

---

## 4. 주요 페이지

```text
StrategyListPage:
저장된 전략 목록

StrategyBuilderPage:
레고형 전략 생성/수정

BacktestRunPage:
전략 선택 후 백테스트 실행 조건 설정

BacktestResultPage:
백테스트 결과 차트/리포트

StrategyComparePage:
여러 전략 결과 비교
```

---

## 5. Strategy Builder 컴포넌트

```text
StrategyBuilderPage
├─ StrategyHeader
├─ BlockPalette
├─ StrategyCanvas
│  ├─ EntrySection
│  ├─ ExitSection
│  ├─ FilterSection
│  ├─ CashManagementSection
│  └─ BacktestDefaultSection
├─ ConditionEditorPanel
├─ StrategyPreviewPanel
└─ StrategyValidationPanel
```

---

## 6. BlockPalette

조건 블록 목록을 표시합니다.

데이터는 API에서 가져옵니다.

```text
GET /api/conditions
```

기능:

```text
카테고리별 조건 표시
검색
즐겨찾기 조건
조건 클릭 시 전략 캔버스에 추가
```

---

## 7. StrategyCanvas

사용자가 만든 전략을 카드로 표시합니다.

섹션:

```text
매수 조건
매도 조건
필터 조건
자금 관리
백테스트 설정
```

조건 카드는 문장형으로 표시합니다.

```text
종가가 20일 이동평균선보다 높을 때
거래량이 20일 평균 거래량의 2배 이상일 때
RSI(14)가 70 이하일 때
```

---

## 8. ConditionEditorPanel

선택한 조건의 파라미터를 수정합니다.

입력 폼은 조건 메타데이터 기반으로 자동 생성합니다.

```json
{
  "name": "ma_period",
  "label": "이동평균 기간",
  "input_type": "number",
  "default": 20
}
```

---

## 9. StrategyPreviewPanel

전략 자연어 설명을 표시합니다.

예:

```text
이 전략은 상승 추세에 있는 종목 중에서 거래량이 급증하고 RSI가 과열되지 않은 종목을 매수합니다.
매수 후 +7% 수익이 나면 익절하고 -3% 손실이 나면 손절합니다.
```

---

## 10. StrategyValidationPanel

오류/경고를 표시합니다.

오류:

```text
매수 조건이 없습니다.
필수 파라미터가 비어 있습니다.
```

경고:

```text
손절 조건이 없습니다.
거래대금 필터가 없습니다.
시장 지수 필터가 없습니다.
```

---

## 11. BacktestRunPage

백테스트 실행 조건을 설정합니다.

구성:

```text
전략 선택
전략 미리보기
시장/종목군 선택
기간 선택
초기 자금
수수료/세금/슬리피지
유니버스 미리보기
실행 전 점검
백테스트 실행
```

---

## 12. UniverseSelector 컴포넌트

지원 옵션:

```text
코스피 전체
코스닥 전체
코스피+코스닥 전체
관심종목
직접 선택
시가총액 상위 N종목
거래대금 상위 N종목
```

시가총액 상위 N종목 선택 시:

```text
시장 선택
상위 N개 입력
선정 기준 선택
유니버스 미리보기
```

---

## 13. BacktestResultPage

결과 화면 탭:

```text
요약
포트폴리오 전체
종목별 상세
거래 내역
자금 관리
CSV 다운로드
```

---

## 14. 차트 컴포넌트

```text
CandleTradeChart:
봉차트, 이동평균선, 매수/매도 마커

EquityCurveChart:
전략 누적 수익률, 벤치마크 수익률

DrawdownChart:
MDD 그래프

CashChart:
예수금 변화

VolumeChart:
거래량
```

---

## 15. 차트 UX 원칙

```text
봉차트 위에는 매수/매도 마커만 기본 표시한다.
수익률 숫자는 계속 표시하지 않는다.
수익률은 6개월 또는 1년 단위로만 표시한다.
상세 정보는 마우스 오버 툴팁으로 표시한다.
```

---

## 16. TradeTable

거래 내역 테이블 컬럼:

```text
종목
매수일
매수가
수량
매도일
매도가
수익률
손익
보유일
매도 사유
```

기능:

```text
정렬
필터
검색
거래 클릭 시 차트 이동
CSV 다운로드
```

---

## 17. 상태 관리

추천:

```text
TanStack Query:
API 데이터 캐싱

React local state:
전략 편집 중 임시 상태

Zustand 선택:
전략 빌더 복잡도 증가 시 사용
```

---

## 18. 타입 정의

```text
types/strategy.ts
types/backtest.ts
types/market.ts
```

예:

```ts
export type Strategy = {
  id: number;
  name: string;
  description?: string;
  strategyJson: StrategyJson;
};

export type Condition = {
  type: string;
  [key: string]: unknown;
};
```

---

## 19. MVP 범위

```text
전략 목록
전략 생성/수정
조건 카드 추가/수정/삭제
전략 저장
백테스트 실행
요약 결과
거래 내역
봉차트 + 매수/매도 마커
CSV 다운로드
```

---

## 20. 테스트 항목

```text
조건 블록 목록 표시
조건 추가
조건 수정
전략 JSON 생성
전략 저장 API 호출
백테스트 실행 API 호출
결과 요약 표시
거래 내역 표시
차트 마커 표시
CSV 다운로드 버튼 표시
```
