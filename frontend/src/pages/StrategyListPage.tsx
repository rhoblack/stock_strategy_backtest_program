import { Link } from "react-router-dom";

/**
 * 전략 목록 페이지 placeholder.
 * 실제 목록 + CRUD UI는 Phase 3 후속 step에서.
 */
export default function StrategyListPage() {
  return (
    <div style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>주식 전략 연구소</h1>
      <p>저장된 전략 목록 (구현 예정).</p>
      <p>
        <Link to="/strategies/new">＋ 새 전략 만들기</Link>
      </p>
    </div>
  );
}
