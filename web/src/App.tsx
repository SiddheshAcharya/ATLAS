import { lazy, Suspense } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import Sidebar from "./components/Sidebar";

// Route-level code splitting: Cytoscape (most of the bundle) loads only with the graph
// view, not with the home page or the report.
const Home = lazy(() => import("./pages/Home"));
const RunLayout = lazy(() => import("./pages/RunLayout"));
const RunView = lazy(() => import("./pages/RunView"));
const PaperDetailPage = lazy(() => import("./pages/PaperDetailPage"));
const ReportView = lazy(() => import("./pages/ReportView"));
const ChatView = lazy(() => import("./pages/ChatView"));

function Loading() {
  return (
    <div className="flex h-full min-h-[40vh] items-center justify-center text-sm text-ink-500">
      Loading…
    </div>
  );
}

export default function App() {
  const { pathname } = useLocation();
  return (
    <>
      {/* outside the boundary: the menu still works if a view crashes */}
      <Sidebar />
      <ErrorBoundary resetKey={pathname}>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/runs/:runId" element={<RunLayout />}>
              <Route index element={<RunView />} />
              <Route path="paper/:paperId" element={<PaperDetailPage />} />
              <Route path="report" element={<ReportView />} />
              <Route path="chat" element={<ChatView />} />
            </Route>
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </>
  );
}
