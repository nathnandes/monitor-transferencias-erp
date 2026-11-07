

function semBarraFinal(url: string): string {
  return url.replace(/\/+$/, "");
}


export const backendUrl = semBarraFinal(import.meta.env.VITE_API_URL ?? "");

export const env = {

  apiBaseUrl: import.meta.env.DEV ? "" : backendUrl,

  timezone: import.meta.env.VITE_TIMEZONE || "America/Porto_Velho",
} as const;
