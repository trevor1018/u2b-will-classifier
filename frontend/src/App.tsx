import { useEffect } from "react";
import { Search } from "lucide-react";
import { useStore } from "./lib/store";
import { loadCases } from "./lib/dataLoader";
import { Header } from "./components/Header";
import { FilterBar } from "./components/FilterBar";
import { CaseDetailDrawer } from "./components/CaseDetailDrawer";
import { MapView } from "./views/MapView";
import { SunburstView } from "./views/SunburstView";
import { TimelineView } from "./views/TimelineView";
import { BubbleView } from "./views/BubbleView";

function App() {
  const setData = useStore((s) => s.setData);
  const setLoading = useStore((s) => s.setLoading);
  const setError = useStore((s) => s.setError);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);

  useEffect(() => {
    setLoading(true);
    loadCases()
      .then(setData)
      .catch((err) => setError(err.message ?? String(err)));
  }, [setData, setLoading, setError]);

  return (
    <div className="min-h-screen bg-ink-950 text-gray-100">
      <Header />
      <main className="mx-auto max-w-[1600px] px-4 pb-20">
        {error && (
          <div className="mt-4 rounded-md border border-accent-danger/40 bg-accent-danger/10 px-4 py-3 text-sm">
            載入失敗：{error}
          </div>
        )}
        {loading ? (
          <div className="flex items-center justify-center py-32 text-gray-400">
            <Search className="mr-2 h-5 w-5 animate-pulse" />
            正在解密檔案…
          </div>
        ) : (
          <>
            <FilterBar />
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
              <Panel className="lg:col-span-8" title="案件地圖" subtitle="GEO-MAP">
                <MapView />
              </Panel>
              <Panel className="lg:col-span-4" title="類型 × 狀態" subtitle="SUNBURST">
                <SunburstView />
              </Panel>
              <Panel className="lg:col-span-12" title="案件年代分布" subtitle="CHRONOLOGY">
                <TimelineView />
              </Panel>
              <Panel className="lg:col-span-12" title="觀眾熱度" subtitle="ENGAGEMENT">
                <BubbleView />
              </Panel>
            </div>
          </>
        )}
      </main>
      <Footer />
      <CaseDetailDrawer />
    </div>
  );
}

function Panel({
  className = "",
  title,
  subtitle,
  children,
}: {
  className?: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`case-card overflow-hidden ${className}`}>
      <header className="flex items-center justify-between border-b border-ink-700/60 px-4 py-2">
        <div>
          <h2 className="text-sm font-bold tracking-wide text-gray-100">{title}</h2>
          <span className="evidence-tag">// {subtitle}</span>
        </div>
      </header>
      <div className="relative">{children}</div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-ink-700/60 bg-ink-900 py-6">
      <div className="mx-auto max-w-[1600px] px-4 text-xs text-gray-500">
        <p>
          非官方粉絲專案 · 致敬{" "}
          <a
            href="https://www.youtube.com/@xdiaocha"
            target="_blank"
            rel="noreferrer"
            className="text-accent-neon hover:underline"
          >
            X調查 (Will)
          </a>
          。所有案件資料為頻道介紹過之公開內容；本站僅彙整 metadata + 縮圖
          + 連回原影片，未重製內容、非營利。
        </p>
      </div>
    </footer>
  );
}

export default App;
