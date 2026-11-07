

import type { Frescor } from "../types/api";
import { getJson } from "./apiClient";

export function getFrescor(signal?: AbortSignal): Promise<Frescor> {
  return getJson<Frescor>("/api/v1/frescor", { signal });
}
