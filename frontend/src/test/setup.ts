import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { cloneElement, createElement, isValidElement, type ReactNode } from "react";
import { afterEach, vi } from "vitest";



vi.mock("recharts", async (importOriginal) => {
  const original = await importOriginal<typeof import("recharts")>();
  return {
    ...original,
    ResponsiveContainer: ({ children, height }: { children: ReactNode; height?: number | string }) => {
      const altura = typeof height === "number" ? height : 260;
      return createElement(
        "div",
        { style: { width: 800, height: altura } },
        isValidElement<{ width?: number; height?: number }>(children)
          ? cloneElement(children, { width: 800, height: altura })
          : children,
      );
    },
  };
});



vi.mock("../services/frescorService", () => ({
  getFrescor: vi.fn(() => Promise.resolve({ gerado_em: "2026-10-14T12:00:00Z", tipos: [] })),
}));



configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  cleanup();
});
