import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useBuilderMode } from "./useBuilderMode";

describe("useBuilderMode", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("default = expert (현재 동작 유지)", () => {
    const { result } = renderHook(() => useBuilderMode());
    expect(result.current.mode).toBe("expert");
    expect(result.current.isExpert).toBe(true);
    expect(result.current.isBeginner).toBe(false);
  });

  it("setMode + localStorage 영속화", () => {
    const { result, rerender } = renderHook(() => useBuilderMode());
    act(() => result.current.setMode("beginner"));
    expect(result.current.mode).toBe("beginner");
    expect(window.localStorage.getItem("stockstrategy.builder_mode")).toBe("beginner");

    // 새 hook 인스턴스도 localStorage에서 읽음
    rerender();
    const { result: r2 } = renderHook(() => useBuilderMode());
    expect(r2.current.mode).toBe("beginner");
  });

  it("toggle — beginner ↔ expert", () => {
    const { result } = renderHook(() => useBuilderMode());
    expect(result.current.mode).toBe("expert");
    act(() => result.current.toggle());
    expect(result.current.mode).toBe("beginner");
    act(() => result.current.toggle());
    expect(result.current.mode).toBe("expert");
  });

  it("잘못된 localStorage 값은 default로 fallback", () => {
    window.localStorage.setItem("stockstrategy.builder_mode", "garbage");
    const { result } = renderHook(() => useBuilderMode());
    expect(result.current.mode).toBe("expert");
  });
});
