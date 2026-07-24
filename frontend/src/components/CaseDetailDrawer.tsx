import { ExternalLink, X } from "lucide-react";
import { useStore } from "../lib/store";
import {
  CASE_TYPE_COLOR,
  CASE_TYPE_LABEL,
  STATUS_COLOR,
  STATUS_LABEL,
} from "../lib/types";

export function CaseDetailDrawer() {
  const focusedCaseId = useStore((s) => s.focusedCaseId);
  const cases = useStore((s) => s.cases);
  const focus = useStore((s) => s.focusCase);

  const c = focusedCaseId ? cases.find((x) => x.id === focusedCaseId) : null;
  if (!c) return null;

  const ytEmbed = `https://www.youtube.com/embed/${c.id}`;

  // Sibling episodes of the same multi-part case (上/下集), ordered 上→下.
  const siblings = c.episodeGroup
    ? cases
        .filter((x) => x.episodeGroup === c.episodeGroup)
        .sort((a, b) => (a.episodeIndex ?? 0) - (b.episodeIndex ?? 0))
    : [];

  return (
    // z-[1000] beats Leaflet's controls (which sit at ~1000) and any other
    // map-internal panes, so the drawer always stacks on top regardless of
    // which panel the user clicked from.
    <div
      className="fixed inset-0 z-[1000] flex justify-end bg-black/70 backdrop-blur-sm"
      onClick={() => focus(null)}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md overflow-y-auto border-l border-ink-700 bg-ink-900 p-5 shadow-2xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <span className="evidence-tag">CASE FILE · {c.id}</span>
            <h2 className="mt-1 text-lg font-bold leading-tight">{c.caseName}</h2>
          </div>
          <button
            onClick={() => focus(null)}
            className="rounded-md p-1 text-gray-400 hover:bg-ink-700 hover:text-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-3 flex flex-wrap gap-1.5">
          <span
            className="rounded-md px-2 py-0.5 text-xs font-medium"
            style={{ backgroundColor: CASE_TYPE_COLOR[c.caseType] + "33", color: CASE_TYPE_COLOR[c.caseType] }}
          >
            {CASE_TYPE_LABEL[c.caseType]}
          </span>
          <span
            className="rounded-md px-2 py-0.5 text-xs font-medium"
            style={{ backgroundColor: STATUS_COLOR[c.status] + "33", color: STATUS_COLOR[c.status] }}
          >
            {STATUS_LABEL[c.status]}
          </span>
          {c.memberOnly && (
            <span className="rounded-md bg-yellow-500/20 px-2 py-0.5 text-xs font-medium text-yellow-400">
              🔒 會員專屬
            </span>
          )}
        </div>

        {siblings.length > 1 && (
          <div className="mb-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-xs text-sky-400">
              📑 多集案件 · 共 {siblings.length} 集
            </div>
            <div className="flex flex-wrap gap-1.5">
              {siblings.map((s) => {
                const active = s.id === c.id;
                return (
                  <button
                    key={s.id}
                    onClick={() => focus(s.id)}
                    className={
                      "rounded-md border px-3 py-1 text-xs font-medium transition " +
                      (active
                        ? "border-accent-neon bg-accent-neon/15 text-accent-neon"
                        : "border-ink-700 text-gray-400 hover:border-ink-600 hover:text-gray-200")
                    }
                  >
                    {active ? "▶ " : ""}
                    {s.episodeLabel}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="aspect-video overflow-hidden rounded-md border border-ink-700 bg-black">
          <iframe
            src={ytEmbed}
            className="h-full w-full"
            allowFullScreen
            title={c.caseName}
          />
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <Row label="案發年份" value={c.crimeYear?.toString() ?? "—"} />
          <Row label="結案年份" value={c.resolveYear?.toString() ?? "—"} />
          <Row label="國家" value={c.country ?? "—"} />
          <Row label="城市" value={c.city ?? "—"} />
          <Row label="觀看數" value={c.viewCount.toLocaleString()} />
          <Row label="按讚數" value={c.likeCount.toLocaleString()} />
          <Row label="留言數" value={c.commentCount.toLocaleString()} />
          <Row
            label="發布"
            value={new Date(c.publishedAt).toLocaleDateString("zh-Hant")}
          />
        </dl>

        {c.description && (
          <p className="mt-4 rounded-md border border-ink-700 bg-ink-950 p-3 text-xs leading-relaxed text-gray-400">
            {c.description}
          </p>
        )}

        <a
          href={c.url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-md border border-accent-neon bg-accent-neon/10 px-4 py-2 text-sm font-medium text-accent-neon transition hover:bg-accent-neon/20"
        >
          <ExternalLink className="h-4 w-4" /> 在 YouTube 觀看
        </a>
      </aside>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-gray-500">{label}</dt>
      <dd className="text-gray-200">{value}</dd>
    </>
  );
}
