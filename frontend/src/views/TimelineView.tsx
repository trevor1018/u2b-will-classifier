import { useCallback, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { ArrowLeft, BarChart3, BarChartHorizontal, RotateCcw } from "lucide-react";
import { useFilteredCases, useStore } from "../lib/store";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  type CaseType,
} from "../lib/types";

// Three-mode timeline:
//  - histogram: stacked bars by decade (alt view)
//  - gantt: case-type swimlanes 1900→2026 with x-axis year scrubber
//    (default, all cases visible at once)
//  - drill-down: triggered by clicking a case-type label on the gantt
//    y-axis. Shows every case of that type on its own row, sorted by
//    crime year, with the case name printed next to the bar's end.
//    Vertical scroll inside the panel when there are many cases.
//
// Pre-1900 cases are bucketed (histogram) or clamped to 1900 (gantt).

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
// 1.5x the previous 300px chart height per user request
const PANEL_CHART_HEIGHT = 450;
// Drill-down: each case row this tall; chart grows + scrolls
const DRILL_ROW_HEIGHT = 24;
// Tag → readable label for inverse lookup on axis-label clicks
const LABEL_TO_TYPE = new Map<string, CaseType>(
  ALL_CASE_TYPES.map((t) => [CASE_TYPE_LABEL[t], t]),
);

type Mode = "hist" | "gantt";

export function TimelineView() {
  const cases = useFilteredCases();
  const yearRange = useStore((s) => s.yearRange);
  const setYearRange = useStore((s) => s.setYearRange);
  const focus = useStore((s) => s.focusCase);
  const [mode, setMode] = useState<Mode>("gantt");
  const [drilledType, setDrilledType] = useState<CaseType | null>(null);

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

  // ---------- Gantt overview (12 swimlanes, all types) ----------
  const ganttOverviewOption = useMemo(() => {
    if (drilledType) return null; // skip building when drilled
    const items = cases
      .filter((c) => typeof c.crimeYear === "number")
      .map((c) => {
        const realStart = c.crimeYear!;
        const realEnd =
          typeof c.resolveYear === "number" && c.resolveYear >= realStart
            ? c.resolveYear
            : realStart + 0.5;
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
      // No tooltip on the overview — the dense 12-lane chart is for
      // pattern-spotting, not per-case inspection. Drill into a type
      // (click the y-axis label) to enable per-case hover.
      tooltip: { show: false },
      grid: { left: 80, right: 20, top: 12, bottom: 56 },
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
        { type: "inside", xAxisIndex: 0, start: 0, end: 100 },
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
          // Lime accent so labels read as clickable; triggerEvent makes
          // them emit click events. Rich-text wrapper was interfering
          // with params.value, so just keep the label plain.
          color: "#a3e635",
          fontSize: 11,
          fontWeight: 600,
          triggerEvent: true,
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: true, lineStyle: { color: "#1f2937" } },
      },
      series: [
        {
          type: "custom",
          // Disable hover highlight on overview bars (matches "no hover"
          // in this mode — pattern-only, not per-case interaction).
          emphasis: { disabled: true },
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
              // Bar visuals don't take hover (tooltip already off,
              // emphasis disabled). NOT setting silent because that was
              // suspected of swallowing axis-label clicks too.
              style: api.style({ opacity: 0.75 }),
            };
          },
          encode: { x: [1, 2], y: 0 },
          data: items,
        },
      ],
    };
  }, [cases, drilledType]);

  // ---------- Drill-down (single type, 1 row per case) ----------
  const drillData = useMemo(() => {
    if (!drilledType) return null;
    const filtered = cases
      .filter(
        (c) =>
          c.caseType === drilledType && typeof c.crimeYear === "number",
      )
      .sort((a, b) => (a.crimeYear ?? 0) - (b.crimeYear ?? 0));
    return filtered;
  }, [cases, drilledType]);

  const drillOption = useMemo(() => {
    if (!drilledType || !drillData || drillData.length === 0) return null;
    const items = drillData.map((c, idx) => {
      const realStart = c.crimeYear!;
      const realEnd =
        typeof c.resolveYear === "number" && c.resolveYear >= realStart
          ? c.resolveYear
          : realStart + 0.5;
      const start = Math.max(GANTT_MIN_YEAR, realStart);
      const end = Math.max(GANTT_MIN_YEAR + 0.5, realEnd);
      return {
        name: c.caseName,
        value: [
          idx, // y row
          start,
          end,
          c.caseType,
          c.id,
          c.country ?? "?",
          realStart,
          realEnd,
          c.caseName, // [8] for inline text rendering
        ],
        itemStyle: { color: CASE_TYPE_COLOR[c.caseType] },
      };
    });
    const allYears = items.flatMap((d) => [
      d.value[1] as number,
      d.value[2] as number,
    ]);
    const maxYear = Math.max(...allYears);

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
          return `<div style="font-weight:700;color:#f3f4f6;">${escapeHtml(p.data.name)}</div>
            <div style="font-size:11px;color:#9ca3af;">${escapeHtml(v[5] as string)} · ${span}</div>`;
        },
      },
      grid: { left: 24, right: 240, top: 8, bottom: 8 },
      xAxis: {
        type: "value",
        min: GANTT_MIN_YEAR - 1,
        max: Math.ceil(maxYear) + 2,
        position: "top",
        axisLabel: {
          color: "#9ca3af",
          fontSize: 10,
          formatter: (v: number) =>
            Math.round(v) === GANTT_MIN_YEAR
              ? `≤${GANTT_MIN_YEAR}`
              : Math.round(v).toString(),
        },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#1f2937" } },
      },
      yAxis: {
        type: "category",
        data: items.map((_, i) => `${i}`),
        inverse: true,
        show: false, // case names rendered inline next to each bar instead
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
            const barHeight = Math.max(6, Math.min(14, rowHeight * 0.55));
            const width = Math.max(2, end[0] - start[0]);
            const caseName = String(api.value(8));
            return {
              type: "group",
              children: [
                {
                  type: "rect",
                  shape: {
                    x: start[0],
                    y: start[1] - barHeight / 2,
                    width,
                    height: barHeight,
                  },
                  style: api.style({ opacity: 0.85 }),
                },
                {
                  type: "text",
                  style: {
                    x: end[0] + 8,
                    y: start[1],
                    text: caseName,
                    fill: "#e5e7eb",
                    font: '500 11px "Noto Sans TC", system-ui, sans-serif',
                    textAlign: "left",
                    textVerticalAlign: "middle",
                  },
                  silent: true,
                },
              ],
            };
          },
          encode: { x: [1, 2], y: 0 },
          data: items,
        },
      ],
    };
  }, [drilledType, drillData]);

  // ---------- Event handlers ----------
  const handleHistEvents = {
    click: (params: { name?: string }) => {
      if (!params.name) return;
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

  // Inspect any click and route to drill if it looks like an axis label.
  const tryDrillFromParams = useCallback(
    (p: {
      componentType?: string;
      targetType?: string;
      value?: string | number;
      name?: string;
    }): boolean => {
      // eslint-disable-next-line no-console
      console.log("[Timeline gantt click]", p);

      // Several shapes the params can take depending on what was clicked
      const candidates: string[] = [];
      if (typeof p.value === "string") candidates.push(p.value);
      if (typeof p.name === "string") candidates.push(p.name);
      for (const cand of candidates) {
        const stripped = cand.replace(/^\{[^|]+\|(.+)\}$/, "$1").trim();
        const t = LABEL_TO_TYPE.get(stripped);
        if (t) {
          setDrilledType(t);
          return true;
        }
      }
      return false;
    },
    [],
  );

  const handleGanttEvents = useMemo(
    () => ({
      click: (p: {
        componentType?: string;
        targetType?: string;
        value?: string | number;
        name?: string;
        data?: { value?: unknown[] };
      }) => {
        if (tryDrillFromParams(p)) return;
        // Bar click — overview disables emphasis/tooltip but click can
        // still fire on the rect. We don't focus from overview.
      },
    }),
    [tryDrillFromParams],
  );

  // Belt-and-braces: also bind a chart-level click that catches axis-label
  // events even if the React onEvents prop misses them for some reason.
  // Typed as any so we can use the (event, query, handler) overload without
  // wrestling ECharts' overloaded signatures here.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onGanttChartReady = useCallback((chart: any) => {
    chart.off("click");
    chart.on("click", { componentType: "yAxis" }, (params: unknown) => {
      tryDrillFromParams(
        params as { componentType?: string; value?: string | number; name?: string },
      );
    });
  }, [tryDrillFromParams]);

  const handleDrillEvents = {
    click: (p: { data?: { value?: unknown[] } }) => {
      const id = p.data?.value?.[4];
      if (typeof id === "string") focus(id);
    },
  };

  // ---------- Render ----------
  const resetAll = () => {
    setMode("gantt");
    setDrilledType(null);
    setYearRange(null);
  };

  const switchMode = (m: Mode) => {
    setMode(m);
    if (drilledType) setDrilledType(null);
  };

  const empty =
    drilledType
      ? !drillOption
      : mode === "hist"
        ? !histOption
        : !ganttOverviewOption;

  // Drilled chart height = N cases × row height, scrollable.
  const drilledChartHeight = drillData
    ? Math.max(PANEL_CHART_HEIGHT, drillData.length * DRILL_ROW_HEIGHT + 30)
    : PANEL_CHART_HEIGHT;

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 border-b border-ink-700/60 px-3 py-1.5">
        <div className="flex items-center gap-2">
          {drilledType && (
            <button
              type="button"
              onClick={() => setDrilledType(null)}
              className="flex items-center gap-1.5 rounded-md border border-ink-700 bg-ink-900/90 px-2 py-1 text-xs text-gray-300 transition hover:border-accent-neon hover:text-accent-neon"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>返回</span>
              <span
                className="ml-1 rounded px-1 py-0.5 text-[10px] font-bold"
                style={{
                  backgroundColor: CASE_TYPE_COLOR[drilledType] + "33",
                  color: CASE_TYPE_COLOR[drilledType],
                }}
              >
                {CASE_TYPE_LABEL[drilledType]} · {drillData?.length ?? 0}
              </span>
            </button>
          )}
        </div>
        <div className="flex gap-2">
          {/* Mode toggle (disabled in drill) */}
          <div className="flex gap-0.5 rounded-md border border-ink-700 bg-ink-900/90 p-0.5">
            <ToolbarBtn
              active={!drilledType && mode === "hist"}
              onClick={() => switchMode("hist")}
              title="長條圖（依年代統計案件數）"
            >
              <BarChart3 className="h-4 w-4" />
            </ToolbarBtn>
            <ToolbarBtn
              active={!drilledType && mode === "gantt"}
              onClick={() => switchMode("gantt")}
              title="甘特圖（每案件一條時間軸）"
            >
              <BarChartHorizontal className="h-4 w-4" />
            </ToolbarBtn>
          </div>
          <div className="flex gap-0.5 rounded-md border border-ink-700 bg-ink-900/90 p-0.5">
            <ToolbarBtn
              onClick={resetAll}
              title="重置視圖（回到預設甘特圖、清除年代篩選）"
            >
              <RotateCcw className="h-4 w-4" />
            </ToolbarBtn>
          </div>
        </div>
      </div>

      {empty ? (
        <div
          className="flex items-center justify-center text-sm text-gray-500"
          style={{ height: PANEL_CHART_HEIGHT }}
        >
          該篩選下沒有可繪製的案發年份資料
        </div>
      ) : drilledType ? (
        // Drill-down: scrollable, chart height grows with case count
        <div
          className="overflow-y-auto"
          style={{ maxHeight: PANEL_CHART_HEIGHT }}
        >
          <div style={{ height: drilledChartHeight }}>
            <ReactECharts
              option={drillOption!}
              style={{ height: "100%", width: "100%" }}
              opts={{ renderer: "canvas" }}
              onEvents={handleDrillEvents}
              notMerge
            />
          </div>
        </div>
      ) : (
        <div style={{ height: PANEL_CHART_HEIGHT }}>
          <ReactECharts
            option={mode === "hist" ? histOption! : ganttOverviewOption!}
            style={{ height: "100%", width: "100%" }}
            opts={{ renderer: "canvas" }}
            onEvents={mode === "hist" ? handleHistEvents : handleGanttEvents}
            onChartReady={mode === "gantt" ? onGanttChartReady : undefined}
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
