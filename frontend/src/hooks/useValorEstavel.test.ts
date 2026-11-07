import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useValorEstavel } from "./useValorEstavel";

describe("useValorEstavel", () => {
  it("devolve a mesma referência enquanto o conteúdo não muda", () => {
    const { result, rerender } = renderHook(({ empresa }) => useValorEstavel({ empresa, periodo: "hoje" }), {
      initialProps: { empresa: "01" },
    });
    const primeiro = result.current;

    rerender({ empresa: "01" });
    expect(result.current).toBe(primeiro);

    rerender({ empresa: "03" });
    expect(result.current).not.toBe(primeiro);
    expect(result.current).toEqual({ empresa: "03", periodo: "hoje" });
  });
});
