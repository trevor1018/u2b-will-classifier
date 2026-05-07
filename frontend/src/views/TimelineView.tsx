import { useEffect, useMemo, useRef } from "react";
import { DataSet, Timeline } from "vis-timeline/standalone";
import { useFilteredCases, useStore } from "../lib/store";
import { CASE_TYPE_COLOR, CASE_TYPE_LABEL } from "../lib/types";

interface TimelineItem {
  id: string;
  group: number;
  start: string;
  end?: string;
  content: string;
  title: string;
  style: string;
}

export function TimelineView() {
  const cases = useFilteredCases();
  const focus = useStore((s) => s.focusCase);
  const containerRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<Timeline | null>(null);
  // Hold a stable ref to the items DataSet so we don't have to fish it back
  // out of vis-timeline's (private-ish) `itemsData` getter — that breaks under
  // some minified prod builds.
  const itemsDSRef = useRef<DataSet<TimelineItem> | null>(null);
  const focusRef = useRef(focus);
  focusRef.current = focus;

  const items = useMemo<TimelineItem[]>(() => {
    const out: TimelineItem[] = [];
    cases.forEach((c) => {
      const color = CASE_TYPE_COLOR[c.caseType];
      const startYear = c.crimeYear;
      const endYear = c.resolveYear ?? c.crimeYear;
      if (startYear) {
        out.push({
          id: `${c.id}-case`,
          group: 1,
          start: `${startYear}-01-01`,
          end: endYear ? `${endYear}-12-31` : undefined,
          content: c.caseName,
          title: `${c.caseName}（${CASE_TYPE_LABEL[c.caseType]}）${startYear}${
            endYear && endYear !== startYear ? `–${endYear}` : ""
          }`,
          style: `background-color: ${color}33; border-color: ${color}; color: #f3f4f6;`,
        });
      }
      out.push({
        id: `${c.id}-pub`,
        group: 2,
        start: c.publishedAt,
        content: `📺 ${c.caseName}`,
        title: `影片發布：${new Date(c.publishedAt).toLocaleDateString("zh-Hant")}`,
        style: `background-color: ${color}55; border-color: ${color}; color: #f3f4f6;`,
      });
    });
    return out;
  }, [cases]);

  // Init once
  useEffect(() => {
    if (!containerRef.current) return;
    const itemsDS = new DataSet<TimelineItem>([]);
    const groupsDS = new DataSet([
      { id: 1, content: "案件壽命", style: "color: #a3e635; font-weight: 600;" },
      { id: 2, content: "影片發布", style: "color: #60a5fa; font-weight: 600;" },
    ]);
    const tl = new Timeline(containerRef.current, itemsDS, groupsDS, {
      stack: true,
      stackSubgroups: false,
      orientation: { axis: "top", item: "top" },
      zoomMin: 1000 * 60 * 60 * 24 * 30,
      zoomMax: 1000 * 60 * 60 * 24 * 365 * 200,
      margin: { item: 4, axis: 6 },
      tooltip: { followMouse: true },
    });
    tl.on("click", (props: { item?: string }) => {
      if (!props.item) return;
      const id = String(props.item).replace(/-(case|pub)$/, "");
      focusRef.current(id);
    });
    timelineRef.current = tl;
    itemsDSRef.current = itemsDS;
    return () => {
      tl.destroy();
      timelineRef.current = null;
      itemsDSRef.current = null;
    };
  }, []);

  // Update items when filtered cases change
  useEffect(() => {
    const ds = itemsDSRef.current;
    const tl = timelineRef.current;
    if (!ds || !tl) return;
    ds.clear();
    ds.add(items);
    if (items.length > 0) tl.fit({ animation: false });
  }, [items]);

  return (
    <div className="px-2 py-3">
      <div ref={containerRef} className="h-[260px]" />
    </div>
  );
}
