import { useState, useCallback } from "react";
import { useConditions } from "../../../api/conditions";
import { useStrategyDraft } from "../state/StrategyDraftContext";
import type { ConditionMeta } from "../../../types/condition";

// localStorage key for favorites
const FAVORITES_KEY = "blockpalette_favorites";

function loadFavorites(): Set<string> {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as string[];
    return new Set(arr);
  } catch {
    return new Set();
  }
}

function saveFavorites(favs: Set<string>): void {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favs]));
  } catch {
    // storage quota 초과 등 — silent fail
  }
}

/**
 * 조건 블록 팔레트 (01-l: 검색/즐겨찾기 포함, step 067).
 *
 * - 검색 입력란: 조건 이름/설명 대소문자 무관 필터링
 * - 즐겨찾기 토글: 별 아이콘 클릭으로 토글, localStorage에 영속화
 * - 필터 탭: "전체" / "즐겨찾기만"
 * - 클릭 시 allowed_in의 첫 섹션으로 ADD_CONDITION dispatch
 */
export default function BlockPalette() {
  const { data, isLoading, error } = useConditions();
  const { dispatch } = useStrategyDraft();

  const [searchQuery, setSearchQuery] = useState("");
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [favorites, setFavorites] = useState<Set<string>>(() => loadFavorites());

  const toggleFavorite = useCallback((type: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      saveFavorites(next);
      return next;
    });
  }, []);

  if (isLoading) return <aside aria-label="블록 팔레트">로딩 중...</aside>;
  if (error || !data)
    return (
      <aside aria-label="블록 팔레트" style={{ color: "crimson" }}>
        조건 카탈로그 불러오기 실패
      </aside>
    );

  // 필터링: 검색어 + 즐겨찾기 탭
  const query = searchQuery.trim().toLowerCase();
  const filtered = data.filter((cond) => {
    if (showFavoritesOnly && !favorites.has(cond.type)) return false;
    if (!query) return true;
    return (
      cond.name.toLowerCase().includes(query) ||
      cond.description.toLowerCase().includes(query)
    );
  });

  // 카테고리별 그룹
  const grouped = new Map<string, ConditionMeta[]>();
  for (const cond of filtered) {
    if (!grouped.has(cond.category)) grouped.set(cond.category, []);
    grouped.get(cond.category)!.push(cond);
  }

  return (
    <aside
      aria-label="블록 팔레트"
      style={{ borderRight: "1px solid #e5e7eb", padding: 12, overflowY: "auto" }}
    >
      <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>블록 팔레트</h2>

      {/* 검색 입력란 */}
      <input
        type="search"
        aria-label="조건 검색"
        placeholder="조건 검색..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        style={{
          width: "100%",
          boxSizing: "border-box",
          padding: "6px 8px",
          border: "1px solid #d1d5db",
          borderRadius: 4,
          fontSize: 13,
          marginBottom: 8,
        }}
      />

      {/* 필터 탭: 전체 / 즐겨찾기만 */}
      <div role="tablist" aria-label="블록 팔레트 필터" style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        <button
          type="button"
          role="tab"
          aria-selected={!showFavoritesOnly}
          onClick={() => setShowFavoritesOnly(false)}
          style={{
            flex: 1,
            padding: "4px 0",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            fontSize: 12,
            cursor: "pointer",
            background: !showFavoritesOnly ? "#3b82f6" : "transparent",
            color: !showFavoritesOnly ? "#fff" : "inherit",
          }}
        >
          전체
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={showFavoritesOnly}
          onClick={() => setShowFavoritesOnly(true)}
          aria-label="즐겨찾기만 보기"
          style={{
            flex: 1,
            padding: "4px 0",
            border: "1px solid #d1d5db",
            borderRadius: 4,
            fontSize: 12,
            cursor: "pointer",
            background: showFavoritesOnly ? "#3b82f6" : "transparent",
            color: showFavoritesOnly ? "#fff" : "inherit",
          }}
        >
          즐겨찾기
        </button>
      </div>

      {/* 결과 없음 */}
      {filtered.length === 0 && (
        <p style={{ fontSize: 12, color: "#6b7280", textAlign: "center", marginTop: 16 }}>
          {showFavoritesOnly ? "즐겨찾기한 조건이 없습니다." : "검색 결과가 없습니다."}
        </p>
      )}

      {/* 카테고리별 조건 목록 */}
      {[...grouped.entries()].map(([category, items]) => (
        <section key={category} style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 12, color: "#6b7280", textTransform: "uppercase" }}>{category}</h3>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((item) => (
              <li key={item.type} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {/* 즐겨찾기 토글 버튼 */}
                <button
                  type="button"
                  aria-label={favorites.has(item.type) ? `${item.name} 즐겨찾기 해제` : `${item.name} 즐겨찾기`}
                  onClick={() => toggleFavorite(item.type)}
                  style={{
                    flexShrink: 0,
                    width: 20,
                    height: 20,
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    fontSize: 14,
                    color: favorites.has(item.type) ? "#f59e0b" : "#d1d5db",
                    padding: 0,
                    lineHeight: 1,
                  }}
                >
                  {favorites.has(item.type) ? "\u2605" : "\u2606"}
                </button>

                {/* 조건 추가 버튼 */}
                <button
                  type="button"
                  onClick={() =>
                    dispatch({
                      type: "ADD_CONDITION",
                      section: item.allowed_in[0],
                      meta: item,
                    })
                  }
                  title={`${item.description}\n클릭하여 ${item.allowed_in[0]} 영역에 추가`}
                  style={{
                    flex: 1,
                    textAlign: "left",
                    padding: "6px 8px",
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    fontSize: 13,
                    borderRadius: 4,
                  }}
                >
                  {item.name}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
