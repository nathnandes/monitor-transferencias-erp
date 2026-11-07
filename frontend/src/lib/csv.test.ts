import { describe, expect, it } from "vitest";

import { celulaCsv, montarCsv } from "./csv";

describe("csv", () => {
  it("formata decimais com vírgula e sem zeros à direita", () => {
    expect(celulaCsv("1234.50")).toBe("1234,5");
    expect(celulaCsv("80000.00")).toBe("80000");
    expect(celulaCsv(-3.25)).toBe("-3,25");
    expect(celulaCsv("1234")).toBe("1234");
  });

  it("protege texto com separador ou aspas e deixa vazio o nulo", () => {
    expect(celulaCsv('LOJA "A"; CENTRO')).toBe('"LOJA ""A""; CENTRO"');
    expect(celulaCsv(null)).toBe("");
  });

  it("começa com BOM e usa ; e CRLF", () => {
    expect(montarCsv(["Código", "Valor"], [["10", "2.5"]])).toBe("﻿Código;Valor\r\n10;2,5\r\n");
  });
});
