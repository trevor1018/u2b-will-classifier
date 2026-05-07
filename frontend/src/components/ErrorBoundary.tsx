import { Component, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Catches render-time errors anywhere below. Without this, a single throw
 *  blanks the whole page in production with no clue. With this, you see what
 *  blew up and where. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error("[ErrorBoundary]", error, info);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-ink-950 p-6 text-gray-100">
          <div className="mx-auto max-w-3xl">
            <h1 className="mb-2 text-lg font-bold text-accent-danger">
              ⚠ 案件分類器當機了
            </h1>
            <p className="mb-4 text-sm text-gray-400">
              開瀏覽器 DevTools 的 Console 看完整 stack trace。
            </p>
            <pre className="overflow-x-auto rounded-md border border-ink-700 bg-ink-900 p-4 font-mono text-xs text-accent-danger">
              {String(this.state.error?.stack ?? this.state.error)}
            </pre>
            <button
              onClick={() => this.setState({ error: null })}
              className="mt-4 rounded-md border border-accent-neon px-3 py-1 text-xs text-accent-neon hover:bg-accent-neon/10"
            >
              重試
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
