# Frontend

레고형 주식 매매 전략 생성 및 백테스트 프로그램의 프론트엔드. React + TypeScript + Vite.

상위 디렉토리의 `상세설계/11_frontend_architecture_design.md` 단일 출처 따름.

## 환경 셋업

Node 20 이상 권장 (개발 환경: v24).

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (백엔드 :8000으로 /api 프록시)
```

백엔드는 별도 터미널에서:

```bash
cd backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

## 자주 쓰는 명령

```bash
npm run dev          # 개발 서버 (포트 5173)
npm run build        # tsc + vite build → dist/
npm run preview      # 빌드 결과 미리보기
npm test             # vitest 1회 실행
npm run test:watch   # vitest watch
```

## 디렉토리 구조

설계서 11번 3절을 따름.

```text
src/
  api/         axios client + TanStack Query hooks
  app/         App.tsx, router 등 앱 부트스트랩
  types/       TypeScript 타입 (백엔드 응답 형식)
  pages/       라우팅 단위 페이지 (StrategyListPage / StrategyBuilderPage / BacktestRunPage / BacktestResultPage)
  features/
    strategy-builder/   BlockPalette / StrategyCanvas / ConditionEditorPanel / Preview / Validation
    backtest-result/    SummaryCards / CandleTradeChart / EquityCurveChart / TradeTable / CsvExportPanel
  components/  공통 UI / layout / charts
  main.tsx     엔트리
  test-setup.ts  vitest 셋업
```

설계서 11번에 정의된 `hooks/`, `utils/`, `features/universe-selector/`, `StrategyComparePage` 등은 향후 작업 후보 (외부 리뷰 4.11 / H6 참조).
