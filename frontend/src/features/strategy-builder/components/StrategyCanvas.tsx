/**
 * 가운데 전략 조립 영역 placeholder.
 * Step 4~5에서 EntrySection / ExitSignalSection / ExitPositionSection /
 * FilterSection / CashManagementSection 카드 빌더로 채움.
 */
export default function StrategyCanvas() {
  return (
    <main aria-label="전략 조립 영역" style={{ padding: 16, overflowY: "auto" }}>
      <h2 style={{ fontSize: 14, fontWeight: 600 }}>전략 조립 영역</h2>

      {(["매수 조건", "매도 시계열 조건", "매도 포지션 조건", "필터", "자금 관리"] as const).map(
        (label) => (
          <section
            key={label}
            style={{
              marginTop: 16,
              padding: 12,
              border: "1px dashed #d1d5db",
              borderRadius: 6,
            }}
          >
            <h3 style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>{label}</h3>
            <p style={{ fontSize: 12, color: "#9ca3af" }}>
              왼쪽 팔레트에서 조건을 추가하세요 (구현 예정).
            </p>
          </section>
        ),
      )}
    </main>
  );
}
