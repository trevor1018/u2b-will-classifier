import { Github, Search, Youtube } from "lucide-react";
import { useStore } from "../lib/store";

export function Header() {
  const payload = useStore((s) => s.payload);
  const cases = useStore((s) => s.cases);

  return (
    <header className="sticky top-0 z-30 border-b border-ink-700/60 bg-ink-950/90 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent-neon/10 ring-1 ring-accent-neon/30">
            <Search className="h-5 w-5 text-accent-neon" />
          </div>
          <div>
            <h1 className="text-base font-bold leading-tight tracking-wide">
              X調查 <span className="text-accent-neon">案件分類器</span>
            </h1>
            <p className="evidence-tag">
              {payload ? (
                <>
                  // {cases.length} 件 · 來源：
                  {payload.source === "mock" ? "MOCK DATA" : "YOUTUBE-LIVE"}
                </>
              ) : (
                "// LOADING…"
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <a
            href="https://www.youtube.com/@xdiaocha"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-md border border-ink-700 px-3 py-1.5 text-gray-300 transition hover:border-accent-danger hover:text-accent-danger"
          >
            <Youtube className="h-4 w-4" />
            <span>原頻道</span>
          </a>
          <a
            href={import.meta.env.VITE_REPO_URL || "https://github.com/trevor1018/u2b-will-classifier"}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-md border border-ink-700 px-3 py-1.5 text-gray-300 transition hover:border-accent-neon hover:text-accent-neon"
          >
            <Github className="h-4 w-4" />
            <span>原始碼</span>
          </a>
        </div>
      </div>
    </header>
  );
}
