import type { ConditionInstance } from "../state/types";

/**
 * sentence_template 문자열의 {placeholder}를 values로 치환.
 * select 파라미터의 경우 options에서 label을 찾아 치환 ({name}_label도 지원).
 *
 * 예: "{price_field}가 {ma_period}일 이동평균선보다 {operator_label}"
 *      → values=adj_close, 20, > → "수정 종가가 20일 이동평균선보다 위"
 */
export function renderSentence(instance: ConditionInstance): string {
  const { meta, values } = instance;

  // 빠른 lookup용
  const paramByName = new Map(meta.parameters.map((p) => [p.name, p]));

  return meta.sentence_template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key: string) => {
    // key가 "_label"로 끝나면 select label 치환
    if (key.endsWith("_label")) {
      const baseName = key.slice(0, -"_label".length);
      const param = paramByName.get(baseName);
      if (param?.input_type === "select" && param.options) {
        const v = values[baseName];
        const opt = param.options.find((o) => o.value === v);
        return opt ? opt.label : String(v ?? "");
      }
      // operator_label 같은 별칭 케이스: operator의 select 라벨
      const altParam = paramByName.get(baseName);
      if (altParam?.input_type === "select" && altParam.options) {
        const v = values[baseName];
        const opt = altParam.options.find((o) => o.value === v);
        return opt ? opt.label : String(v ?? "");
      }
      return String(values[baseName] ?? "");
    }

    // 일반 치환
    const v = values[key];
    if (v === undefined || v === null) return `{${key}}`;

    // select면 가독성을 위해 label로 변환
    const param = paramByName.get(key);
    if (param?.input_type === "select" && param.options) {
      const opt = param.options.find((o) => o.value === v);
      if (opt) return opt.label;
    }
    return String(v);
  });
}
