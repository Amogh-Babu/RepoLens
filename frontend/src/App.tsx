import {Route, Routes} from 'react-router';
import {AnalysisPage} from './pages/AnalysisPage.tsx';
import {LandingPage} from './pages/LandingPage.tsx';
import {NotFoundPage} from './pages/NotFoundPage.tsx';

/** Top-level routes. The router itself is provided by the caller. */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/analysis/:analysisId" element={<AnalysisPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
