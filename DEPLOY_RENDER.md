# Free deployment checklist

TRANA uses direct Quick Thinking provider analysis. It tries configured GPT-OSS
providers first, then Llama-compatible routes. The normal chat path does not load a local
vector database, embeddings, BM25, or a reranker.

## 1. Deploy the backend on Render

1. Open Render Dashboard and choose **New -> Blueprint**.
2. Connect GitHub and select `krish-chauhan-1108/legal-rag-advisor-2` on `main`.
3. Review `render.yaml` and apply the Blueprint.
4. Existing Google deployments may keep the Gemini key variables:
   `GEMINI_API_KEY`, `GEMINI_API_KEY_FALLBACK`, `GEMINI_API_KEY_3`, and
   `GEMINI_API_KEY_4`.
   Optional provider bootstrap variables are `GROQ_API_KEY`,
   `CEREBRAS_API_KEY`; additional keys and all routing
   priority should be managed through the private admin console.
5. Set `GOOGLE_CLIENT_ID` to the OAuth web-client ID used by the frontend.
6. Open `/health` and confirm `status` is `healthy` and
   `source_registry_ready` is `true`.

The old `/api/ingest`, `/api/documents`, and seed-import endpoints are retained
only as compatibility routes and return `410 Gone`. They do not initialize the
old RAG stack.

## 2. Configure durable chat history

Set `DATABASE_URL` in Render to a hosted PostgreSQL connection string. SQLite
on the free Render filesystem is ephemeral and should only be used for local
testing.

## 3. Configure the private admin console

The admin console is available at `/admin` on the Vercel frontend. It requires
a verified Google sign-in and an email listed in `ADMIN_EMAILS`.

Also set `API_KEY_ENCRYPTION_KEY` in Render. Generate one locally with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The service imports configured legacy Gemini and optional provider variables
into encrypted key pools without duplicating existing fingerprints. Usage
counters track TRANA's provider attempts by key, provider, model, minute, and
IST day; they do not show
usage made by the same keys elsewhere in Google AI Studio.

## 4. Point Vercel at the backend

1. In Vercel project settings, set `VITE_API_URL` to the Render service URL
   without a trailing slash for Production and Preview.
2. Redeploy. Vite embeds this value during the build.
3. Sign in, open chat, and confirm the backend health indicator is ready.

## 5. Exact legal-source behavior

The model may identify a likely Act and section, but it never supplies
authoritative quotation text. The backend clears model-generated quotes and
hydrates exact wording only when the citation exists in
`legal_sources/corpus.json`, whose records are hash-validated at startup.

The checked-in corpus currently contains reviewed Section 1(1) samples for
BNS, BNSS, and BSA. Citations outside that corpus remain visibly unverified;
they must not be presented as word-for-word statutory text until authoritative
records are added and reviewed.

## 6. Keep the free Render service warm

Use an independent uptime monitor such as UptimeRobot to send an HTTPS `GET`
request to:

```text
https://legal-rag-advisor-api.onrender.com/health
```

Configure the monitor to run every 5 minutes and expect an HTTP 2xx response.
This reduces cold-start delays for the demo, but it does not guarantee
availability during Render restarts, maintenance, or free-plan limits.
It uses roughly 720 hours of the free service's 750-hour monthly allowance,
leaving little room for other free services.

Do not deploy a second free Render service that pings the main service while
the main service pings it back. Both services can sleep independently, and
mutual outbound requests do not reliably keep either service running. The
existing `scripts/keep-render-alive.ps1` file remains available as a local
fallback for manual testing when a machine is online; it is not the primary
keep-alive mechanism.
