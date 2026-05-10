/**
 * 공통 PageHeader (11-f) — 페이지 상단의 "← 이전" 링크 + 제목 + 부제 패턴 추출.
 *
 * 기존 페이지에서 반복되는 ☆ Link("← 전략 목록") + h1 패턴을 점진적으로 대체.
 * 본 step에서는 정의만 노출; 호출부 마이그레이션은 후속.
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export type PageHeaderProps = {
  title: string;
  /** 우측 액션 (예: "+ 새 전략 만들기" 링크/버튼). */
  actions?: ReactNode;
  /** 부제 / 안내 텍스트. */
  subtitle?: ReactNode;
  /** 뒤로 가기 링크 (없으면 미표시). */
  backTo?: { to: string; label: string };
};

export default function PageHeader({
  title,
  actions,
  subtitle,
  backTo,
}: PageHeaderProps) {
  return (
    <header style={{ marginBottom: 12 }}>
      {backTo && (
        <p style={{ marginBottom: 4 }}>
          <Link to={backTo.to} style={{ color: "#6b7280", fontSize: 13 }}>
            ← {backTo.label}
          </Link>
        </p>
      )}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{title}</h1>
        {actions && <div style={{ display: "flex", gap: 8 }}>{actions}</div>}
      </div>
      {subtitle && (
        <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>{subtitle}</div>
      )}
    </header>
  );
}
