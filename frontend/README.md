# Stillroom web app

Next.js app with two separate workspaces: Writing keeps the chapter editor and continuity assistant; Editing is a structured file library for uploading, organizing, previewing, and downloading story drafts without editing their contents in the app.

## Run locally

1. Start the backend from `backend/` on `http://127.0.0.1:8000`.
2. Start Ollama and pull `nomic-embed-text` for local scene indexing.
3. Set `OPENROUTER_API_KEY` in `backend/.env` if you want the writer-controlled external analysis features.
4. Install frontend dependencies with `npm install`.
5. Run `npm run dev` from this directory and open `http://localhost:3000`.

For a backend on another host, set `BACKEND_API_URL` before starting/building Next.js. The Next.js rewrite keeps the browser API same-origin so the HTTP-only session cookie is sent correctly.

Next's rewrite proxy aborts a response after 30 seconds unless told otherwise, which is shorter than a slow model reply. `BACKEND_PROXY_TIMEOUT_MS` (default `150000`) sets the limit; keep it above the backend's `OPENROUTER_TIMEOUT_SECONDS`. Without it, a continuity check that takes 31-90 seconds finishes and saves its findings on the server but the browser reports a failed request.

The Writing workspace contains no prose-generation action. External analysis must be explicitly enabled per story, and the continuity scanner compares the active chapter only against earlier chapters. The Editing workspace stores original files in PostgreSQL, organizes them into folders, and offers read-only browser previews for PDF and text drafts. Files in Editing are not indexed or sent to AI analysis.
