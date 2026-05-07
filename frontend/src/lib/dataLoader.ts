import type { CasesPayload } from "./types";

/** Loads the cases JSON from /public/data/cases.json (Vite respects base prefix). */
export async function loadCases(): Promise<CasesPayload> {
  const url = `${import.meta.env.BASE_URL}data/cases.json`;
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`Failed to load cases.json (${res.status} ${res.statusText})`);
  }
  return (await res.json()) as CasesPayload;
}
