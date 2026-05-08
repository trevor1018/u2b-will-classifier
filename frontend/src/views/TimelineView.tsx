import { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { BarChart3, BarChartHorizontal } from "lucide-react";
import { useFilteredCases, useStore } from "../lib/store";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  type CaseType,
} from "../lib/types";

// Two views over the same case-set, switchable via the top-right toggle:
//  - histogram (default): stacked-bar count by decade, click a decade to
//    set the year-range filter
//  - gantt: each case is a horizontal bar in its case-type swimlane,
//    spanning crimeYear → resolveYear; gives a left-to-right sense of
//    time progression and which decades are dense

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

type Mode = "hist" | "gantt";

export function TimelineView() {
  const cases = useFilteredCases();
  const yearRange = useStore((s) => s.yearRange);
  const setYearRange = useStore((s) => s.setYearRange);
  const focus = useStore((s) => s.focusCase);
  const [mode, setMode] = useState<Mode>("hist");

  const histOption = useMemo(() => {
    const decadeOf = (y: number) => Math.floor(y / 10) * 10;
    const years = cases
      .map((c) => c.crimeYear)
      .filter((y): y is number => typeof y === "number");
    if (years.length === 0) return null;

    const minDecade = decadeOf(Math.min(...years));
    const maxDecade = decadeOf(Math.max(...years));
    const decades: number[] = [];
    for (let d = minDecade; d <= maxDecade; d += 10) decades.push(d);

    const countsByType = new Map<CaseType, number[]>();
    for (const t of ALL_CASE_TYPES) {
      countsByType.set(t, decades.map(() => 0));
    }
    for (const c of cases) {
      if (typeof c.crimeYear !== "number") continue;
      const idx = decades.indexOf(decadeOf(c.crimeYear));
      if (idx < 0) continue;
      const arr = countsByType.get(c.caseType);
      if (arr) arr[idx]++;
    }

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
      _decades: decades, // pinned for click handler
    };
  }, [cases, yearRange]);

  const ganttOption = useMemo(() => {
    const items = cases
      .filter((c) => typeof c.crimeYear === "number")
      .map((c) => {
        const start = c.crimeYear!;
        const end =
          typeof c.resolveYear === "number" && c.resolveYear >= start
            ? c.resolveYear
            : start + 0.5; // tiny tick for un-resolved / instant cases
        return {
          name: c.caseName,
          value: [
            ALL_CASE_TYPES.indexOf(c.caseType), // y idx
            start,
            end,
            c.caseType,
            c.id,
            c.country ?? "?",
          ],
          itemStyle: { color: CASE_TYPE_COLOR[c.caseType] },
        };
      });
    if (items.length === 0) return null;

    const allYears = items.flatMap((d) => [
      d.value[1] as number,
      d.value[2] as number,
    ]);
    const minYear = Math.min(...allYears);
    const maxYear = Math.max(...allYears);
    // Pad ±2 years so edge bars aren't clipped
    const xMin = Math.floor(minYear) - 2;
    const xMax = Math.ceil(maxYear) + 2;

    return {
      backgroundColor: "transparent",
      tooltip: {
        backgroundColor: "#0b1018",
        borderColor: "#1f2937",
        textStyle: { color: "#f3f4f6", fontSize: 12 },
        formatter: (p: { data: { name: string; value: unknown[] } }) => {
          const v = p.data.value;
          const start = v[1] as number;
          const end = v[2] as number;
          const span = end - start > 0.5 ? `${start}–${Math.floor(end)}` : `${start}`;
          const t = v[3] as CaseType;
          return `<div style="font-size:11px;color:#a3e635;text-transform:uppercase;letter-spacing:.05em;">${CASE_TYPE_LABEL[t]}</div>
            <div style="font-weight:700;color:#f3f4f6;">${escapeHtml(p.data.name)}</div>
            <div style="font-size:11px;color:#9ca3af;">${escapeHtml(v[5] as string)} · ${span}</div>`;
        },
      },
      grid: { left: 80, right: 20, top: 12, bottom: 32 },
      xAxis: {
        type: "value",
        min: xMin,
        max: xMax,
        axisLabel: {
          color: "#9ca3af",
          fontSize: 10,
          formatter: (v: number) => Math.round(v).toString(),
        },
        axisLine: { lineStyle: { color: "#374151" } },
        splitLine: { lineStyle: { color: "#1f2937" } },
      },
      yAxis: {
        type: "category",
        data: ALL_CASE_TYPES.map((t) => CASE_TYPE_LABEL[t]),
        inverse: true,
        axisLabel: {
          color: "#9ca3af",
          fontSize: 11,
          fontWeight: 600,
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: true, lineStyle: { color: "#1f2937" } },
      },
      series: [
        {
          type: "custom",
          renderItem: (
            _params: unknown,
            api: {
              value: (i: number) => number | string;
              coord: (v: [number | string, number | string]) => [number, number];
              size: (v: [number, number]) => [number, number];
              style: (extra?: Record<string, unknown>) => Record<string, unknown>;
              visual: (k: string) => string;
            },
          ) => {
            const yIdx = api.value(0) as number;
            const x0 = api.value(1) as number;
            const x1 = api.value(2) as number;
            const start = api.coord([x0, yIdx]);
            const end = api.coord([x1, yIdx]);
            const rowHeight = api.size([0, 1])[1];
            const barHeight = Math.max(4, rowHeight * 0.45);
            const width = Math.max(2, end[0] - start[0]);
            return {
              type: "rect",
              shape: {
                x: start[0],
                y: start[1] - barHeight / 2,
                width,
                height: barHeight,
              },
              style: api.style({ opacity: 0.75 }),
            };
          },
          encode: { x: [1, 2], y: 0 },
          data: items,
        },
      ],
    };
  }, [cases]);

  const handleHistEvents = {
    click: (params: { name?: string }) => {
      if (!params.name) return;
      const decadeStart = parseInt(params.name, 10);
      if (isNaN(decadeStart)) return;
      const newRange: [number, number] = [decadeStart, decadeStart + 9];
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

  const handleGanttEvents = {
    click: (p: { data?: { value?: unknown[] } }) => {
      const id = p.data?.value?.[4];
      if (typeof id === "string") focus(id);
    },
  };

  const empty = mode === "hist" ? !histOption : !ganttOption;

  return (
    <div className="relative">
      {/* Mode toggle — top-right, sits above the chart */}
      <div className="absolute right-3 top-2 z-10 flex gap-1 rounded-md border border-ink-700 bg-ink-900/90 p-0.5 backdrop-blur">
        <button
          type="button"
          onClick={() => setMode("hist")}
          title="長條圖（依年代統計案件數）"
          className={`flex h-7 w-7 items-center justify-center rounded transition ${
            mode === "hist"
              ? "bg-accent-neon/15 text-accent-neon"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          <BarChart3 className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => setMode("gantt")}
          title="甘特圖（每案件一條時間軸）"
          className={`flex h-7 w-7 items-center justify-center rounded transition ${
            mode === "gantt"
              ? "bg-accent-neon/15 text-accent-neon"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          <BarChartHorizontal className="h-4 w-4" />
        </button>
      </div>

      {empty ? (
        <div className="flex h-[280px] items-center justify-center text-sm text-gray-500">
          該篩選下沒有可繪製的案發年份資料
        </div>
      ) : (
        <div className="h-[320px]">
          <ReactECharts
            option={mode === "hist" ? histOption! : ganttOption!}
            style={{ height: "100%", width: "100%" }}
            opts={{ renderer: "canvas" }}
            onEvents={mode === "hist" ? handleHistEvents : handleGanttEvents}
            notMerge
          />
        </div>
      )}
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (m) =>
    m === "&"
      ? "&amp;"
      : m === "<"
        ? "&lt;"
        : m === ">"
          ? "&gt;"
          : m === '"'
            ? "&quot;"
            : "&#39;",
  );
}
