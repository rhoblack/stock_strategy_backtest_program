import type { StrategyDraft, Section, SectionState } from "../state/types";
import { renderSentence } from "./renderSentence";

const SECTION_HEADER: Record<Section, string> = {
  entry: "매수 조건",
  exit_signal: "지표 기반 매도",
  exit_position: "포지션 기반 매도",
  filters: "필터",
};

function logicLabel(section: SectionState): string {
  if (section.conditions.length <= 1) return "";
  return section.logic === "AND" ? "(모두 만족)" : "(하나라도 만족)";
}

/**
 * 사람이 읽는 자연어 전략 설명 생성.
 * 빈 섹션은 출력하지 않음.
 */
export function buildPreviewText(draft: StrategyDraft): string[] {
  const lines: string[] = [];

  for (const section of ["entry", "exit_signal", "exit_position", "filters"] as Section[]) {
    const sec = draft.sections[section];
    if (sec.conditions.length === 0) continue;

    lines.push(`${SECTION_HEADER[section]} ${logicLabel(sec)}`.trim());
    for (const cond of sec.conditions) {
      lines.push(`  • ${renderSentence(cond)}`);
    }
  }

  if (lines.length === 0) {
    lines.push("아직 조건이 없습니다. 왼쪽 팔레트에서 조건을 추가하세요.");
  }

  return lines;
}
