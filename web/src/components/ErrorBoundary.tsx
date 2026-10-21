import { Component, type ErrorInfo, type ReactNode } from "react";

// One broken panel (a malformed snapshot, a chunk that failed to load) must not blank the
// whole dashboard mid-demo. Shows what went wrong and offers a retry instead.
interface Props {
  children: ReactNode;
  resetKey?: string;
}
interface State {
  error: Error | null;
  key?: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  // navigating to another route clears a previous route's error
  static getDerivedStateFromProps(props: Props, state: State) {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ATLAS view crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="flex h-full min-h-[40vh] items-center justify-center p-6">
        <div className="max-w-lg rounded-lg border border-red-500/30 bg-red-500/10 p-5 text-sm">
          <div className="mb-1 font-medium text-red-200">This view hit an error.</div>
          <div className="mb-4 break-words font-mono text-xs text-red-300/80">
            {this.state.error.message}
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            className="rounded bg-ink-800 px-3 py-1.5 text-ink-200 hover:bg-ink-700"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }
}
