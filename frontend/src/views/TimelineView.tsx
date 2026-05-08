import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useFilteredCases, useStore } from "../lib/store";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  type CaseType,
} from "../lib/types";

// Stacked-bar histogram by decade.
// X = decade buckets, Y = case count, stacked by case type.
//
// At 454 cases the previous per-case range chart was too dense to read.
// This view keeps the time dimension but compresses to "how did case-type
// composition shift across history".
//
// Behaviour:
//  - Respects the current filter (cases already comes pre-filtered)
//  - Click a decade bar → set the year-range filter to that decade
//    (acts as a click-to-filter source as well)
//  - Click again on the active decade → clears the year filter

const ALL_CASE_TYPES: CaseType[] = [
  "murder",
  "missing",
  "serial",
  "kidnap",
  "robbery",
  "escape",
  "fraud",
  "cult",
  "disaster",
  "mystery",
  "curio",
  "other",
];

export function TimelineView() {
  const cases = useFilteredCases();
  const yearRange = useStore((s) => s.yearRange);
  const setYearRange = useStore((s) => s.setYearRange);

  const option = useMemo(() => {
    const decadeOf = (y: number) => Math.floor(y / 10) * 10;
    const years = cases
      .map((c) => c.crimeYear)
      .filter((y): y is number => typeof y === "number");

    if (years.length === 0) {
      return null;
    }

    const minDecade = decadeOf(Math.min(...years));
    const maxDecade = decadeOf(Math.max(...years));

    // Continuous decade list so empty buckets still show as 0 (preserves
    // visual rhythm — gaps between active decades are part of the story).
    const decades: number[] = [];
    for (let d = minDecade; d <= maxDecade; d += 10) decades.push(d);

    const countsByType = new Map<CaseType, number[]>();
    for (const t of ALL_CASE_TYPES) {
      countsByType.set(
        t,
        decades.map(() => 0),
      );
    }
    for (const c of cases) {
      if (typeof c.crimeYear !== "number") continue;
      const idx = decades.indexOf(decadeOf(c.crimeYear));
      if (idx < 0) continue;
      const arr = countsByType.get(c.caseType);
      if (arr) arr[idx]++;
    }

    // Highlight the currently-filtered decade(s) on the X axis labels
    const isInFilteredRange = (decadeStart: number) => {
      if (!yearRange) return false;
      const decadeEnd = decadeStart + 9;
      return decadeStart >= yearRange[0] && decadeEnd <= yearRange[1];
    };

    const series = ALL_CASE_TYPES.flatMap((t) => {
      const data = countsByType.get(t)!;
      if (!data.some((n) => n > 0)) return [];
      return [
        {
          name: CASE_TYPE_LABEL[t],
          type: "bar",
          stack: "total",
          barMaxWidth: 36,
          itemStyle: { color: CASE_TYPE_COLOR[t] },
          emphasis: { focus: "series" },
          data: data.map((n, i) => ({
            value: n,
            // Make non-active-range bars slightly translucent when a year
            // filter is in effect, so the active range pops.
            itemStyle: yearRange
              ? {
                  color: CASE_TYPE_COLOR[t],
                  opacity: isInFilteredRange(decades[i]) ? 1 : 0.3,
                }
              : undefined,
          })),
        },
      ];
    });

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "#0b1018",
        borderColor: "#1f2937",
        textStyle: { color: "#f3f4f6", fontSize: 12 },
      },
      legend: {
        textStyle: { color: "#9ca3af", fontSize: 10 },
        top: 4,
        icon: "circle",
        itemWidth: 8,
        itemHeight: 8,
      },
      grid: { left: 48, right: 20, top: 38, bottom: 32 },
      xAxis: {
        type: "category",
        data: decades.map((d) => `${d}s`),
        axisLabel: { color: "#9ca3af", fontSize: 10, interval: 0 },
        axisLine: { lineStyle: { color: "#374151" } },
      },
      yAxis: {
        type: "value",
        name: "案件數",
        nameTextStyle: { color: "#9ca3af", fontSize: 10 },
        axisLabel: { color: "#9ca3af", fontSize: 10 },
        axisLine: { lineStyle: { color: "#374151" } },
        splitLine: { lineStyle: { color: "#1f2937" } },
      },
      series,
    };
  }, [cases, yearRange]);

  if (!option) {
    return (
      <div className="flex h-[280px] items-center justify-center text-sm text-gray-500">
        該篩選下沒有可繪製的案發年份資料
      </div>
    );
  }

  // Click a decade bar → set year range to that decade. Click the active
  // decade again → clear.
  const handleEvents = {
    click: (params: { name?: string }) => {
      if (!params.name) return;
      const decadeStart = parseInt(params.name, 10);
      if (isNaN(decadeStart)) return;
      const newRange: [number, number] = [decadeStart, decadeStart + 9];
      // Toggle off if the same range is currently set
      if (
        yearRange &&
        yearRange[0] === newRange[0] &&
        yearRange[1] === newRange[1]
      ) {
        setYearRange(null);
      } else {
        setYearRange(newRange);
      }
    },
  };

  return (
    <div className="h-[280px]">
      <ReactECharts
        option={option}
        style={{ height: "100%", width: "100%" }}
        opts={{ renderer: "canvas" }}
        onEvents={handleEvents}
        notMerge={true}
      />
    </div>
  );
}
