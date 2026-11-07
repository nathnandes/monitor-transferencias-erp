

import type { Empresa } from "../types/api";
import { getJson } from "./apiClient";

export function getEmpresas(signal?: AbortSignal): Promise<Empresa[]> {
  return getJson<Empresa[]>("/api/v1/empresas", { signal });
}
