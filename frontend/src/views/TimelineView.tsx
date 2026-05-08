import { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { BarChart3, BarChartHorizontal, RotateCcw } from "lucide-react";
import { useFilteredCases, useStore } from "../lib/store";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  type CaseType,
} from "../lib/types";

// Two views over the same case-set, switchable via the top toolbar:
//  - histogram (default): stacked-bar count by decade
//  - gantt: case-type swimlanes with crimeYear → resolveYear bars
//
// Pre-1900 cases are folded into a single bucket / clamped to 1900 so the
// long sparse tail (1840s-1890s with ≤2 cases each) doesn't stretch the
// x-axis on either chart.

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

const PRE_1900_LABEL = "1900年前";
const GANTT_MIN_YEAR = 1900;

type Mode = "hist" | "gantt";

export function TimelineView() {
  const cases = useFilteredCases();
  const yearRange = useStore((s) => s.yearRange);
  const setYearRange = useStore((s) => s.setYearRange);
  const focus = useStore((s) => s.focusCase);
  // Default to gantt — user finds the left-to-right time progression more
  // useful than the per-decade aggregation. Histogram is the alt view.
  const [mode, setMode] = useState<Mode>("gantt");

  // ---------- Histogram option ----------
  const histOption = useMemo(() => {
    const decadeOf = (y: number) => Math.floor(y / 10) * 10;
    const years = cases
      .map((c) => c.crimeYear)
      .filter((y): y is number => typeof y === "number");
    if (years.length === 0) return null;

    const labels: string[] = [];
    const labelToIdx = new Map<string, number>();
    const hasPre1900 = years.some((y) => y < 1900);
    if (hasPre1900) {
      labelToIdx.set(PRE_1900_LABEL, labels.length);
      labels.push(PRE_1900_LABEL);
    }
    const post1900Years = years.filter((y) => y >= 1900);
    if (post1900Years.length > 0) {
      const minD = decadeOf(Math.min(...post1900Years));
      const maxD = decadeOf(Math.max(...post1900Years));
      for (let d = Math.max(1900, minD); d <= maxD; d += 10) {
        labelToIdx.set(`${d}s`, labels.length);
        labels.push(`${d}s`);
      }
    }

    const labelOf = (y: number) =>
      y < 1900 ? PRE_1900_LABEL : `${decadeOf(y)}s`;

    const countsByType = new Map<CaseType, number[]>();
    for (const t of ALL_CASE_TYPES) {
      countsByType.set(t, labels.map(() => 0));
    }
    for (const c of cases) {
      if (typeof c.crimeYear !== "number") continue;
      const idx = labelToIdx.get(labelOf(c.crimeYear));
      if (idx == null) continue;
      const arr = countsByType.get(c.caseType);
      if (arr) arr[idx]++;
    }

    // Decade-level filter highlighting. Pre-1900 bucket considered
    // "in range" if the filter overlaps any year < 1900.
    const isInFilteredRange = (label: string) => {
      if (!yearRange) return false;
      if (label === PRE_1900_LABEL) return yearRange[0] < 1900;
      const decadeStart = parseInt(label, 10);
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
                  opacity: isInFilteredRange(labels[i]) ? 1 : 0.3,
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
        data: labels,
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

  // ---------- Gantt option ----------
  const ganttOption = useMemo(() => {
    const items = cases
      .filter((c) => typeof c.crimeYear === "number")
      .map((c) => {
        const realStart = c.crimeYear!;
        const realEnd =
          typeof c.resolveYear === "number" && c.resolveYear >= realStart
            ? c.resolveYear
            : realStart + 0.5;
        // Clamp pre-1900 to GANTT_MIN_YEAR for display, keep actual values
        // in tooltip.
        const start = Math.max(GANTT_MIN_YEAR, realStart);
        const end = Math.max(GANTT_MIN_YEAR + 0.5, realEnd);
        return {
          name: c.caseName,
          value: [
            ALL_CASE_TYPES.indexOf(c.caseType),
            start,
            end,
            c.caseType,
            c.id,
            c.country ?? "?",
            realStart,
            realEnd,
          ],
          itemStyle: { color: CASE_TYPE_COLOR[c.caseType] },
        };
      });
    if (items.length === 0) return null;

    const allYears = items.flatMap((d) => [
      d.value[1] as number,
      d.value[2] as number,
    ]);
    const maxYear = Math.max(...allYears);
    const xMin = GANTT_MIN_YEAR - 1;
    const xMax = Math.ceil(maxYear) + 2;

    return {
      backgroundColor: "transparent",
      tooltip: {
        backgroundColor: "#0b1018",
        borderColor: "#1f2937",
        textStyle: { color: "#f3f4f6", fontSize: 12 },
        formatter: (p: { data: { name: string; value: unknown[] } }) => {
          const v = p.data.value;
          const realStart = v[6] as number;
          const realEnd = v[7] as number;
          const span =
            realEnd - realStart > 0.5
              ? `${realStart}–${Math.floor(realEnd)}`
              : `${realStart}`;
          const t = v[3] as CaseType;
          const note =
            realStart < GANTT_MIN_YEAR
              ? `<div style="font-size:10px;color:#fbbf24;">＊1900年前案件，已壓在左軸</div>`
              : "";
          return `<div style="font-size:11px;color:#a3e635;text-transform:uppercase;letter-spacing:.05em;">${CASE_TYPE_LABEL[t]}</div>
            <div style="font-weight:700;color:#f3f4f6;">${escapeHtml(p.data.name)}</div>
            <div style="font-size:11px;color:#9ca3af;">${escapeHtml(v[5] as string)} · ${span}</div>${note}`;
        },
      },
      // Bottom is generous so the dataZoom slider has room without
      // overlapping the x-axis labels.
      grid: { left: 80, right: 20, top: 12, bottom: 56 },
      // Year scrollbar: starts at full range, drag handles to zoom into a
      // narrower window, drag the body or scroll-wheel inside the chart to
      // pan left/right.
      dataZoom: [
        {
          type: "slider",
          xAxisIndex: 0,
          bottom: 6,
          height: 18,
          backgroundColor: "rgba(11, 16, 24, 0.6)",
          fillerColor: "rgba(163, 230, 53, 0.18)",
          borderColor: "#374151",
          handleStyle: { color: "#a3e635", borderColor: "#a3e635" },
          moveHandleStyle: { color: "#a3e635" },
          textStyle: { color: "#9ca3af", fontSize: 9 },
          dataBackground: {
            lineStyle: { color: "#374151" },
            areaStyle: { color: "rgba(163, 230, 53, 0.08)" },
          },
          start: 0,
          end: 100,
        },
        {
          type: "inside",
          xAxisIndex: 0,
          start: 0,
          end: 100,
        },
      ],
      xAxis: {
        type: "value",
        min: xMin,
        max: xMax,
        axisLabel: {
          color: "#9ca3af",
          fontSize: 10,
          formatter: (v: number) =>
            Math.round(v) === GANTT_MIN_YEAR
              ? `≤${GANTT_MIN_YEAR}`
              : Math.round(v).toString(),
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
      // Pre-1900 → range = [1800, 1899] (cover the bucket)
      if (params.name === PRE_1900_LABEL) {
        if (yearRange && yearRange[0] === 1800 && yearRange[1] === 1899) {
          setYearRange(null);
        } else {
          setYearRange([1800, 1899]);
        }
        return;
      }
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

  // Reset to canonical default state.
  const resetAll = () => {
    setMode("gantt");
    setYearRange(null);
  };

  return (
    <div>
      {/* Toolbar — flow layout above the chart so it never overlaps data */}
      <div className="flex items-center justify-end gap-2 border-b border-ink-700/60 px-3 py-1.5">
        {/* Mode toggle */}
        <div className="flex gap-0.5 rounded-md border border-ink-700 bg-ink-900/90 p-0.5">
          <ToolbarBtn
            active={mode === "hist"}
            onClick={() => setMode("hist")}
            title="長條圖（依年代統計案件數）"
          >
            <BarChart3 className="h-4 w-4" />
          </ToolbarBtn>
          <ToolbarBtn
            active={mode === "gantt"}
            onClick={() => setMode("gantt")}
            title="甘特圖（每案件一條時間軸）"
          >
            <BarChartHorizontal className="h-4 w-4" />
          </ToolbarBtn>
        </div>

        {/* Reset */}
        <div className="flex gap-0.5 rounded-md border border-ink-700 bg-ink-900/90 p-0.5">
          <ToolbarBtn
            onClick={resetAll}
            title="重置視圖（回到預設甘特圖、清除年代篩選）"
          >
            <RotateCcw className="h-4 w-4" />
          </ToolbarBtn>
        </div>
      </div>

      {empty ? (
        <div className="flex h-[280px] items-center justify-center text-sm text-gray-500">
          該篩選下沒有可繪製的案發年份資料
        </div>
      ) : (
        <div className="h-[300px]">
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

function ToolbarBtn({
  children,
  onClick,
  title,
  active = false,
  disabled = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`flex h-7 w-7 items-center justify-center rounded transition ${
        disabled
          ? "cursor-not-allowed text-gray-600"
          : active
            ? "bg-accent-neon/15 text-accent-neon"
            : "text-gray-400 hover:text-gray-200"
      }`}
    >
      {children}
    </button>
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
