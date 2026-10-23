import {useEffect, useRef} from 'react';
import {Route, Routes, useLocation} from 'react-router';
import {AppErrorBoundary} from './components/AppErrorBoundary.tsx';
import {AnalysisPage} from './pages/AnalysisPage.tsx';
import {LandingPage} from './pages/LandingPage.tsx';
import {NotFoundPage} from './pages/NotFoundPage.tsx';

/** Top-level routes. The router itself is provided by the caller. */
export function App() {
  const {pathname} = useLocation();
  const firstRender = useRef(true);

  // After client-side navigation, move focus to the new page's content so
  // keyboard and screen reader users start there, as on a full page load.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    document.getElementById('main')?.focus();
  }, [pathname]);

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <AppErrorBoundary key={pathname}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/analysis/:analysisId" element={<AnalysisPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppErrorBoundary>
    </>
  );
}
