import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useFilteredCases, useStore } from "../lib/store";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  STATUS_COLOR,
  STATUS_LABEL,
  type CaseStatus,
  type CaseType,
} from "../lib/types";

interface SunburstNode {
  name: string;
  value?: number;
  children?: SunburstNode[];
  itemStyle?: { color: string; borderColor?: string };
  label?: { color?: string };
  raw?: { type: CaseType; status?: CaseStatus };
}

export function SunburstView() {
  const cases = useFilteredCases();
  const toggleType = useStore((s) => s.toggleCaseType);
  const toggleStatus = useStore((s) => s.toggleStatus);

  const data = useMemo<SunburstNode[]>(() => {
    // Group: type → status → count
    const tree: Record<string, Record<string, number>> = {};
    for (const c of cases) {
      tree[c.caseType] ??= {};
      tree[c.caseType][c.status] = (tree[c.caseType][c.status] ?? 0) + 1;
    }
    return Object.entries(tree).map(([t, statuses]) => ({
      name: CASE_TYPE_LABEL[t as CaseType],
      itemStyle: { color: CASE_TYPE_COLOR[t as CaseType], borderColor: "#06080d" },
      raw: { type: t as CaseType },
      children: Object.entries(statuses).map(([s, n]) => ({
        name: STATUS_LABEL[s as CaseStatus],
        value: n,
        itemStyle: { color: STATUS_COLOR[s as CaseStatus], borderColor: "#06080d" },
        raw: { type: t as CaseType, status: s as CaseStatus },
      })),
    }));
  }, [cases]);

  const option = {
    backgroundColor: "transparent",
    tooltip: { trigger: "item", formatter: "{b}: {c}" },
    series: [
      {
        type: "sunburst",
        radius: ["15%", "92%"],
        sort: undefined,
        emphasis: { focus: "ancestor" },
        data,
        label: {
          color: "#f3f4f6",
          fontSize: 11,
          minAngle: 12,
        },
        levels: [
          {},
          { r0: "15%", r: "55%", label: { rotate: "tangential", fontWeight: 600 } },
          { r0: "55%", r: "92%", label: { rotate: 0, fontSize: 10 } },
        ],
      },
    ],
  };

  return (
    <div className="h-[480px]">
      {cases.length === 0 ? (
        <Empty />
      ) : (
        <ReactECharts
          option={option}
          style={{ height: "100%", width: "100%" }}
          opts={{ renderer: "canvas" }}
          onEvents={{
            click: (params: { data?: SunburstNode }) => {
              const raw = params.data?.raw;
              if (!raw) return;
              if (raw.status) toggleStatus(raw.status);
              else toggleType(raw.type);
            },
          }}
        />
      )}
    </div>
  );
}

function Empty() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-gray-500">
      無資料 — 試試清除篩選條件
    </div>
  );
}
