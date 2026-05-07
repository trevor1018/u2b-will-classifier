import { useEffect, useMemo, useRef } from "react";
import cytoscape, { type Core } from "cytoscape";
import { useFilteredCases, useStore } from "../lib/store";
import { CASE_TYPE_COLOR } from "../lib/types";

export function NetworkView() {
  const cases = useFilteredCases();
  const focus = useStore((s) => s.focusCase);
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const focusRef = useRef(focus);
  focusRef.current = focus;

  const { nodes, edges } = useMemo(() => {
    const nodes = cases.map((c) => ({
      data: {
        id: c.id,
        label: c.caseName,
        color: CASE_TYPE_COLOR[c.caseType],
        size: Math.max(18, Math.log10(Math.max(1, c.viewCount)) * 5),
      },
    }));

    // Build edges: same country & same type & nearby decade
    const edges: { data: { id: string; source: string; target: string; weight: number } }[] = [];
    for (let i = 0; i < cases.length; i++) {
      for (let j = i + 1; j < cases.length; j++) {
        const a = cases[i];
        const b = cases[j];
        let weight = 0;
        if (a.country && a.country === b.country) weight += 1;
        if (a.caseType === b.caseType) weight += 1;
        if (a.crimeYear && b.crimeYear && Math.abs(a.crimeYear - b.crimeYear) <= 5) weight += 1;
        if (a.status === b.status) weight += 0.5;
        if (weight >= 2) {
          edges.push({
            data: {
              id: `${a.id}-${b.id}`,
              source: a.id,
              target: b.id,
              weight,
            },
          });
        }
      }
    }
    return { nodes, edges };
  }, [cases]);

  // Init once
  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "border-color": "#06080d",
            "border-width": 1.5,
            label: "data(label)",
            color: "#f3f4f6",
            "font-size": 9,
            "text-outline-color": "#06080d",
            "text-outline-width": 2,
            "text-valign": "center",
            "text-halign": "center",
            width: "data(size)",
            height: "data(size)",
            "text-wrap": "ellipsis",
            "text-max-width": "70px",
          },
        },
        {
          selector: "edge",
          style: {
            "line-color": "#374151",
            "curve-style": "haystack",
            opacity: 0.4,
            width: "mapData(weight, 2, 4, 1, 3)",
          },
        },
        {
          selector: "node:selected",
          style: { "border-color": "#a3e635", "border-width": 3 },
        },
      ],
      layout: { name: "preset" },
      wheelSensitivity: 0.3,
    });
    cy.on("tap", "node", (e) => {
      focusRef.current(e.target.id());
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  // Update graph elements
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().remove();
    cy.add([...nodes, ...edges]);
    cy.layout({
      name: "cose",
      animate: false,
      idealEdgeLength: () => 80,
      nodeRepulsion: () => 8000,
      gravity: 0.4,
      numIter: 800,
      padding: 30,
    } as cytoscape.LayoutOptions).run();
  }, [nodes, edges]);

  return (
    <div className="relative h-[400px]">
      <div ref={containerRef} className="h-full w-full" />
      {cases.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-gray-500">
          無資料 — 試試清除篩選條件
        </div>
      )}
    </div>
  );
}
