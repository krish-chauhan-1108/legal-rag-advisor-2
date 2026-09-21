# Free deployment checklist

The repository is prepared for a free Render backend and Vercel frontend.

## 1. Deploy the backend on Render

1. Open Render Dashboard and choose **New → Blueprint**.
2. Connect GitHub when prompted and authorize Render for the repository.
3. Select `krish-chauhan-1108/legal-rag-advisor-2` and branch `main`.
4. Review the service from `render.yaml` and apply the Blueprint.
5. In the service's **Environment** page, fill the four secret values:
   - `GEMINI_API_KEY`
   - `GEMINI_API_KEY_FALLBACK`
   - `GEMINI_API_KEY_3`
   - `GEMINI_API_KEY_4`
6. Save changes and wait for the deploy to finish.
7. Open `https://<your-render-service>.onrender.com/health` and confirm it returns
   a healthy JSON response.

## 1a. Import the existing document index

The actual RAG index is `data/chroma_db`; `legal.db` only stores chat/session
metadata. To import the current local snapshot:

1. In Render, set a long random `SEED_UPLOAD_TOKEN` environment variable.
2. Locally run:

   ```powershell
   .\scripts\create_seed_archive.ps1
   ```

   This creates `deployment-seed.zip` from `legal.db`, `data/chroma_db`, and
   any saved PDFs under `data/uploads`. The archive is intentionally ignored by
   Git and must not be committed.
3. Upload it to the deployed service:

   ```powershell
   curl.exe -X POST `
     -H "X-Seed-Token: YOUR_SEED_UPLOAD_TOKEN" `
     -F "archive=@deployment-seed.zip" `
     https://<your-render-service>.onrender.com/api/admin/import-seed
   ```

4. Restart the Render service, then check `/health` to confirm the process is
   healthy. Use `/api/documents` to inspect the
   imported index to load and verify the documents/chunks.

This is a snapshot import, not durable storage. Render's free filesystem can
still be reset when the service is replaced. Keep the ZIP privately so it can
be uploaded again if needed.

## 1b. Configure Google accounts and durable chat history

TRANA verifies Google ID tokens and stores chat sessions by verified email.
Set these variables in Render:

- `GOOGLE_CLIENT_ID`: the Google OAuth web-client ID.
- `DATABASE_URL`: a PostgreSQL connection string, preferably the provider's
  pooled/session connection for Render.

Set the same client ID in Vercel as `VITE_GOOGLE_CLIENT_ID`, and add the Vercel
production URL to the OAuth client's authorized JavaScript origins.

The free Render filesystem is ephemeral. SQLite, uploaded files, and the local
Chroma index can be lost after a redeploy or instance replacement. Re-upload
the knowledge-base documents after such an event, or migrate storage before
using this for persistent production data.

## 1c. Configure the private admin console

The admin console is available at `/admin` on the Vercel frontend. It requires
both a verified Google sign-in and an email listed in these Render variables:

- `ADMIN_EMAILS`: comma-separated Google email addresses allowed to manage keys.
- `API_KEY_ENCRYPTION_KEY`: a Fernet key used to encrypt keys in the hosted database.

Generate the encryption key locally with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add both values in Render's **Environment** page, then redeploy. The first
startup imports any non-empty legacy `GEMINI_API_KEY`,
`GEMINI_API_KEY_FALLBACK`, `GEMINI_API_KEY_3`, and `GEMINI_API_KEY_4` values
into the encrypted key pool without duplicating existing fingerprints.

After signing in with an allowlisted account, use **Account → Admin console**
to add, deactivate, reorder, or delete keys. Raw keys are never returned to
the frontend. Usage counters measure TRANA's own Gemini provider attempts and
are separated by key, model, current minute, and IST calendar day; they do not
include usage made by the same keys elsewhere in Google AI Studio.

## 2. Point Vercel at the backend

1. Open the existing Vercel project.
2. Go to **Settings → Environment Variables**.
3. Add or update `VITE_API_URL` with the Render service URL, without a trailing
   slash, for Production and Preview.
4. Trigger a new deployment from the Vercel **Deployments** page. Vite embeds
   this value during the build, so changing the variable alone does not update
   an already-built deployment.
5. Open the Vercel URL and verify the app loads, documents can be uploaded,
   and a chat request reaches the backend.

## 3. First-use order

After deployment, import the prepared seed archive before
asking a document-grounded question. The backend intentionally rejects analysis
requests while the vector index is empty.
