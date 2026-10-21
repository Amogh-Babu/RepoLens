import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserRouter} from 'react-router';
import {ApiClientContext} from './api/apiClientContext.ts';
import {createApiClient} from './api/createApiClient.ts';
import {App} from './App.tsx';
import './index.css';

const rootElement = document.getElementById('root');
if (rootElement === null) {
  throw new Error('Missing #root element in index.html');
}

const apiClient = createApiClient();

createRoot(rootElement).render(
  <StrictMode>
    <ApiClientContext value={apiClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ApiClientContext>
  </StrictMode>,
);
