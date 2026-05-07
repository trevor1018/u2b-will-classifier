import { useMemo } from "react";
import { X } from "lucide-react";
import { useStore } from "../lib/store";
import type { CaseStatus, CaseType } from "../lib/types";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  STATUS_COLOR,
  STATUS_LABEL,
} from "../lib/types";

export function FilterBar() {
  const cases = useStore((s) => s.cases);
  const caseTypes = useStore((s) => s.caseTypes);
  const statuses = useStore((s) => s.statuses);
  const countries = useStore((s) => s.countries);
  const yearRange = useStore((s) => s.yearRange);
  const searchText = useStore((s) => s.searchText);
  const toggleCaseType = useStore((s) => s.toggleCaseType);
  const toggleStatus = useStore((s) => s.toggleStatus);
  const toggleCountry = useStore((s) => s.toggleCountry);
  const setYearRange = useStore((s) => s.setYearRange);
  const setSearchText = useStore((s) => s.setSearchText);
  const clearFilters = useStore((s) => s.clearFilters);

  const stats = useMemo(() => {
    const types = new Set<CaseType>();
    const stat = new Set<CaseStatus>();
    const ctry = new Set<string>();
    let minY = Infinity;
    let maxY = -Infinity;
    for (const c of cases) {
      types.add(c.caseType);
      stat.add(c.status);
      if (c.country) ctry.add(c.country);
      if (c.crimeYear) {
        if (c.crimeYear < minY) minY = c.crimeYear;
        if (c.crimeYear > maxY) maxY = c.crimeYear;
      }
    }
    return {
      types: Array.from(types),
      statuses: Array.from(stat),
      countries: Array.from(ctry).sort((a, b) => a.localeCompare(b)),
      minYear: isFinite(minY) ? minY : 1900,
      maxYear: isFinite(maxY) ? maxY : new Date().getFullYear(),
    };
  }, [cases]);

  const [yLow, yHigh] = yearRange ?? [stats.minYear, stats.maxYear];
  const hasActive =
    caseTypes.size > 0 ||
    statuses.size > 0 ||
    countries.size > 0 ||
    yearRange !== null ||
    searchText.trim() !== "";

  return (
    <div className="case-card mt-4 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <input
          type="search"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          placeholder="搜尋標題、案件名、國家、城市…"
          className="min-w-[220px] flex-1 rounded-md border border-ink-700 bg-ink-900 px-3 py-1.5 text-sm placeholder:text-gray-500 focus:border-accent-neon focus:outline-none"
        />

        {/* Year range */}
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span className="evidence-tag">YEAR</span>
          <input
            type="number"
            value={yLow}
            min={stats.minYear}
            max={yHigh}
            onChange={(e) => setYearRange([Number(e.target.value), yHigh])}
            className="w-20 rounded border border-ink-700 bg-ink-900 px-2 py-1 text-center"
          />
          <span>—</span>
          <input
            type="number"
            value={yHigh}
            min={yLow}
            max={stats.maxYear}
            onChange={(e) => setYearRange([yLow, Number(e.target.value)])}
            className="w-20 rounded border border-ink-700 bg-ink-900 px-2 py-1 text-center"
          />
        </div>

        {hasActive && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 rounded-md border border-ink-700 px-2 py-1 text-xs text-gray-400 hover:border-accent-danger hover:text-accent-danger"
          >
            <X className="h-3 w-3" /> 清除
          </button>
        )}
      </div>

      {/* Case type chips */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="evidence-tag mr-1">TYPE</span>
        {stats.types.map((t) => {
          const active = caseTypes.has(t);
          return (
            <button
              key={t}
              onClick={() => toggleCaseType(t)}
              style={
                active
                  ? { backgroundColor: CASE_TYPE_COLOR[t], color: "#0b1018" }
                  : { borderColor: CASE_TYPE_COLOR[t] + "55", color: CASE_TYPE_COLOR[t] }
              }
              className="rounded-md border px-2.5 py-1 text-xs font-medium transition hover:brightness-125"
            >
              {CASE_TYPE_LABEL[t]}
            </button>
          );
        })}
      </div>

      {/* Status chips */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="evidence-tag mr-1">STATUS</span>
        {stats.statuses.map((s) => {
          const active = statuses.has(s);
          return (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              style={
                active
                  ? { backgroundColor: STATUS_COLOR[s], color: "#0b1018" }
                  : { borderColor: STATUS_COLOR[s] + "55", color: STATUS_COLOR[s] }
              }
              className="rounded-md border px-2.5 py-1 text-xs font-medium transition hover:brightness-125"
            >
              {STATUS_LABEL[s]}
            </button>
          );
        })}
      </div>

      {/* Country chips (collapsed scroll if many) */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="evidence-tag mr-1">COUNTRY</span>
        {stats.countries.map((c) => {
          const active = countries.has(c);
          return (
            <button
              key={c}
              onClick={() => toggleCountry(c)}
              className={`rounded-md border px-2.5 py-1 text-xs transition ${
                active
                  ? "border-accent-neon bg-accent-neon/15 text-accent-neon"
                  : "border-ink-700 text-gray-400 hover:border-gray-500 hover:text-gray-200"
              }`}
            >
              {c}
            </button>
          );
        })}
      </div>
    </div>
  );
}
