const configuredApiUrl = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL || '';
const productionApiUrl = 'https://legal-rag-advisor-api.onrender.com';

// Long-running Gemini requests should go directly to Render in production.
// The Vercel rewrite is useful for short requests but can time out while the
// deep model is still generating a response.
export const API_URL = import.meta.env.PROD
  ? (configuredApiUrl && configuredApiUrl !== 'http://localhost:8000'
    ? configuredApiUrl.replace(/\/$/, '')
    : productionApiUrl)
  : (configuredApiUrl || 'http://localhost:8000');
