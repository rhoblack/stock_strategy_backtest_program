/**
 * 생존편향 영향 분석 패널 (06-l, step 068).
 *
 * 설계서 06번 §11.2 명세:
 *   "이 백테스트 기간 동안:
 *    - 신규 상장: N개 종목
 *    - 상장폐지: M개 종목
 *    - 상장폐지 데이터를 보유하지 않은 경우 결과가 실제보다 좋게 보일 수 있습니다."
 *
 * 데이터 소스:
 *   - delistingCount: trades에서 exit_reason == "delisting" || "delisting_estimated" 건수
 *   - estimatedCount: delisting_estimated 건수 (경고 강도 판단용)
 *   - newListingCount: 현재 API에서 제공하지 않으므로 미표시 (null이면 "정보 없음")
 *
 * Props:
 *   - delistingCount: 상장폐지 강제매도 건수 (delisting + delisting_estimated 합산)
 *   - estimatedCount: 상장폐지 예정(보수적 추정) 건수 (0.5x 패널티 적용된 건수)
 *   - newListingCount: 신규 상장 편입 건수 (null이면 미표시)
 */

export type SurvivalBiasPanelProps = {
  delistingCount: number;
  estimatedCount: number;
  newListingCount: number | null;
};

export default function SurvivalBiasPanel({
  delistingCount,
  estimatedCount,
  newListingCount,
}: SurvivalBiasPanelProps) {
  const hasWarning = estimatedCount > 0;

  return (
    <section
      aria-label="생존편향 영향 분석"
      style={{
        marginTop: 16,
        padding: "12px 16px",
        background: "#f9fafb",
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        fontSize: 13,
      }}
    >
      <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: "#374151" }}>
        생존편향 영향 분석
      </h3>

      <p style={{ color: "#6b7280", marginBottom: 6 }}>이 백테스트 기간 동안:</p>

      <ul style={{ listStyle: "none", padding: 0, margin: 0, color: "#374151" }}>
        {newListingCount !== null && (
          <li style={{ marginBottom: 4 }}>
            신규 상장: <strong data-testid="new-listing-count">{newListingCount}개</strong> 종목
          </li>
        )}
        <li style={{ marginBottom: 4 }}>
          상장폐지 강제매도:{" "}
          <strong data-testid="delisting-count">{delistingCount}건</strong>
          {estimatedCount > 0 && (
            <span style={{ color: "#b45309", marginLeft: 6 }}>
              (추정 종가 ×0.5 적용: {estimatedCount}건)
            </span>
          )}
        </li>
      </ul>

      {hasWarning && (
        <p
          data-testid="survival-bias-warning"
          style={{
            marginTop: 10,
            padding: "8px 12px",
            background: "#fef3c7",
            border: "1px solid #fcd34d",
            borderRadius: 4,
            color: "#92400e",
            fontSize: 12,
          }}
        >
          상장폐지 데이터를 보유하지 않은 종목이 있어 종가의 50%로 보수적 추정 매도했습니다.
          실제 결과보다 백테스트 성과가 좋게 나타날 수 있습니다.
        </p>
      )}

      {delistingCount === 0 && newListingCount === 0 && (
        <p style={{ marginTop: 8, color: "#9ca3af", fontSize: 12 }}>
          이 기간 중 상장폐지/신규 상장 영향 없음.
        </p>
      )}
    </section>
  );
}
