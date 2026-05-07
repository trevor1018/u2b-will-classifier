import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useFilteredCases, useStore } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL, type CaseType } from "../lib/types";

export function BubbleView() {
  const cases = useFilteredCases();
  const focus = useStore((s) => s.focusCase);

  const seriesData = useMemo(() => {
    const grouped: Record<CaseType, Array<[number, number, number, string, string]>> = {
      murder: [], missing: [], serial: [], cult: [], fraud: [], robbery: [],
      disaster: [], mystery: [], kidnap: [], curio: [], other: [],
    };
    for (const c of cases) {
      const t = new Date(c.publishedAt).getTime();
      const data: [number, number, number, string, string] = [
        t,
        c.viewCount,
        Math.max(8, Math.sqrt(c.likeCount) * 0.6),
        c.id,
        c.caseName,
      ];
      grouped[c.caseType].push(data);
    }
    return Object.entries(grouped)
      .filter(([, arr]) => arr.length > 0)
      .map(([t, arr]) => ({
        name: CASE_TYPE_LABEL[t as CaseType],
        type: "scatter",
        symbolSize: (d: number[]) => d[2],
        data: arr,
        emphasis: {
          itemStyle: { borderColor: "#fff", borderWidth: 2 },
          label: { show: true, formatter: (p: { data: unknown[] }) => p.data[4] as string },
        },
        itemStyle: {
          color: CASE_TYPE_COLOR[t as CaseType],
          opacity: 0.75,
        },
      }));
  }, [cases]);

  const option = {
    backgroundColor: "transparent",
    legend: {
      data: seriesData.map((s) => s.name),
      textStyle: { color: "#9ca3af", fontSize: 10 },
      top: 4,
      icon: "circle",
    },
    grid: { left: 60, right: 24, top: 36, bottom: 40 },
    tooltip: {
      trigger: "item",
      backgroundColor: "#0b1018",
      borderColor: "#1f2937",
      textStyle: { color: "#f3f4f6", fontSize: 12 },
      formatter: (p: { data: unknown[]; marker: string }) => {
        const d = p.data;
        const dt = new Date(d[0] as number).toLocaleDateString("zh-Hant");
        return `${p.marker} <b>${d[4]}</b><br/>發布：${dt}<br/>觀看：${(d[1] as number).toLocaleString()}`;
      },
    },
    xAxis: {
      type: "time",
      name: "影片發布日",
      nameTextStyle: { color: "#9ca3af" },
      axisLabel: { color: "#9ca3af", fontSize: 10 },
      axisLine: { lineStyle: { color: "#374151" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    },
    yAxis: {
      type: "log",
      name: "觀看數",
      nameTextStyle: { color: "#9ca3af" },
      axisLabel: { color: "#9ca3af", fontSize: 10 },
      axisLine: { lineStyle: { color: "#374151" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    },
    series: seriesData,
  };

  return (
    <div className="h-[400px]">
      {cases.length === 0 ? (
        <div className="flex h-full items-center justify-center text-sm text-gray-500">
          無資料
        </div>
      ) : (
        <ReactECharts
          option={option}
          style={{ height: "100%", width: "100%" }}
          opts={{ renderer: "canvas" }}
          onEvents={{
            click: (p: { data?: unknown[] }) => {
              const id = p.data?.[3];
              if (typeof id === "string") focus(id);
            },
          }}
        />
      )}
    </div>
  );
}
