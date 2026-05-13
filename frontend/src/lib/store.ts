import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";
import type { CaseRecord, CaseStatus, CaseType, CasesPayload } from "./types";

interface FilterState {
  /** All cases loaded from /data/cases.json */
  cases: CaseRecord[];
  payload: CasesPayload | null;
  loading: boolean;
  error: string | null;

  /** Active filters (empty set = all) */
  caseTypes: Set<CaseType>;
  statuses: Set<CaseStatus>;
  /** Single-select country (null = all). When set, the map zooms to it. */
  country: string | null;
  yearRange: [number, number] | null; // by crimeYear; null = all
  searchText: string;
  /** Currently focused case (clicked from any view). null = none. */
  focusedCaseId: string | null;

  /** Actions */
  setData: (payload: CasesPayload) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  toggleCaseType: (t: CaseType) => void;
  toggleStatus: (s: CaseStatus) => void;
  toggleCountry: (c: string) => void;
  setYearRange: (r: [number, number] | null) => void;
  setSearchText: (q: string) => void;
  focusCase: (id: string | null) => void;
  clearFilters: () => void;
}

export const useStore = create<FilterState>((set) => ({
  cases: [],
  payload: null,
  loading: true,
  error: null,
  caseTypes: new Set(),
  statuses: new Set(),
  country: null,
  yearRange: null,
  searchText: "",
  focusedCaseId: null,

  setData: (payload) =>
    set({ payload, cases: payload.cases, loading: false, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),

  toggleCaseType: (t) =>
    set((s) => {
      const next = new Set(s.caseTypes);
      next.has(t) ? next.delete(t) : next.add(t);
      return { caseTypes: next };
    }),
  toggleStatus: (st) =>
    set((s) => {
      const next = new Set(s.statuses);
      next.has(st) ? next.delete(st) : next.add(st);
      return { statuses: next };
    }),
  toggleCountry: (c) =>
    set((s) => ({ country: s.country === c ? null : c })),
  setYearRange: (r) => set({ yearRange: r }),
  setSearchText: (q) => set({ searchText: q }),
  focusCase: (id) => set({ focusedCaseId: id }),
  clearFilters: () =>
    set({
      caseTypes: new Set(),
      statuses: new Set(),
      country: null,
      yearRange: null,
      searchText: "",
      focusedCaseId: null,
    }),
}));

/** Apply all active filters to the case list. Pure (no Zustand deps). */
export function applyFilters(state: FilterState): CaseRecord[] {
  const { cases, caseTypes, statuses, country, yearRange, searchText } = state;
  const q = searchText.trim().toLowerCase();
  return cases.filter((c) => {
    if (caseTypes.size > 0 && !caseTypes.has(c.caseType)) return false;
    if (statuses.size > 0 && !statuses.has(c.status)) return false;
    if (country) {
      // A case matches the country filter if its primary country matches
      // OR any of its points sits in that country (compilation case).
      const primary = c.country === country;
      const inPoints = c.points?.some((p) => p.country === country) ?? false;
      if (!primary && !inPoints) return false;
    }
    if (yearRange && c.crimeYear) {
      if (c.crimeYear < yearRange[0] || c.crimeYear > yearRange[1]) return false;
    }
    if (q) {
      const hay = `${c.title} ${c.caseName} ${c.country ?? ""} ${c.city ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/** Hook returning filtered cases. Uses shallow equality so consumers get a
 *  STABLE array reference when filter state hasn't actually changed — without
 *  this, every store update produces a fresh array via filter() and the
 *  components downstream (especially react-leaflet) loop infinitely on
 *  "props changed". */
export function useFilteredCases(): CaseRecord[] {
  return useStore(useShallow(applyFilters));
}
