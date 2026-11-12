# InterviewLens — API Contract (backend ↔ frontend)

App name: **InterviewLens** (NOT HireLens). AI-powered role-based candidate screening:
resume in → RAG over ML textbooks → generated interview questions → interactive
interview → SQLite-persisted Q&A → structured summary.

## Roles (knowledge base is the provided ML books — no generic web text)
- `ai_ml` — AI/ML Engineer. KB: Mitchell (OCR text), Burkov, Bishop, Brownlee.
- `data_science` — Data Science / Applied ML Engineer. KB: Intro to ML with Python,
  Brownlee, ML for Absolute Beginners, Burkov.
- (No Backend Engineer role: the provided books cover ML only; do not invent a KB.)

## Backend: Python FastAPI, port 8000. Venv at project root `.venv`.
## Frontend: React + Vite (plain CSS, no heavy UI lib). Dev port 5173, proxy /api → :8000.
## Data: SQLite at `data/interviewlens.db`. Vector store: FAISS index + chunks JSON
## under `data/vectorstore/` (built by `backend/ingest.py` from `books/`).

## Endpoints
- `GET /api/health` → `{"status":"ok","roles":[...],"chunks":N}`
- `GET /api/roles` → `[{"id":"ai_ml","label":"AI/ML Engineer","books":[...]},
  {"id":"data_science","label":"Data Science / Applied ML Engineer","books":[...]}]`
- `POST /api/sessions` (multipart form: `resume` file .pdf/.txt, `role` string)
  → `{"session_id": str, "parsed": {"skills": [str], "technologies": [str],
  "domains": [str], "name": str|null}, "topics": [str],
  "retrieved_chunks": [{"source": str, "page": int|null, "text": str}],
  "questions": [{"id": str, "text": str, "topic": str, "source": str}]}`
  - Parse resume with pypdf (fallback: plain text). Extract skills by matching a
    curated skill vocabulary against resume text (case-insensitive).
  - Build 3–5 retrieval queries from role + extracted skills/topics.
  - Retrieve top-k (k=3 per query, dedup) chunks from FAISS.
  - Generate 5 questions with the real LLM (google/flan-t5-base, local, CPU)
    prompted with retrieved context + resume skills. NO template-written
    questions: every question must come from the model. If the model fails,
    return HTTP 503 with a clear error — never fall back to templates.
  - Persist session + questions in SQLite. Questions shown one at a time.
- `GET /api/sessions/{id}` → session + questions + answers so far + status.
- `POST /api/sessions/{id}/answers` JSON `{"question_id": str, "answer": str}`
  → `{"ok": true, "next_question": {...}|null}`. Stores the answer in SQLite.
  Adaptive follow-up is OPTIONAL: if implemented, generate at most 1 follow-up
  per answered question from the model using the answer; else return next
  queued question.
- `POST /api/sessions/{id}/finish` → `{"summary": {"questions_asked": int,
  "answered": int, "topics_covered": [str], "strengths": [str],
  "gaps": [str], "overall": str}}` — strengths/gaps derived from simple
  recorded signals only (answer length / keyword overlap with the chunk),
  labelled as basic heuristics in the UI. No invented scores.
- `GET /api/sessions/{id}/summary` → same summary payload (for the results view).

## RAG ingestion (`backend/ingest.py`, runnable standalone)
- Reads `books/*.pdf` (Mitchell via `books/mitchell-ocr.txt` when present, else skip
  Mitchell and log it) + `books/*.txt`.
- Chunking: ~800 chars with 150-char overlap, split on paragraph/section boundaries
  where possible; keep `source` (book title) + `page` metadata.
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (local, CPU).
- Store: FAISS IndexFlatIP on L2-normalised embeddings + `chunks.json`.
- Print chunk counts per book at the end; exit non-zero if total chunks == 0.

## Question generation (`backend/generate.py`)
- Model: `google/flan-t5-base` via transformers, CPU, max_new_tokens ~64,
  temperature ~0.7. Prompt includes: role, candidate skills, 1–2 retrieved
  chunks (truncated to ~1200 chars total), instruction to ask ONE specific
  conceptual-or-applied interview question (no generic "tell me about yourself").
- One model call per question; dedupe near-identical questions.

## Env config (`.env`, never commit secrets)
- `DATABASE_URL` (default sqlite:///./data/interviewlens.db)
- `VECTORSTORE_DIR` (default ./data/vectorstore)
- `EMBEDDING_MODEL` (default sentence-transformers/all-MiniLM-L6-v2)
- `GENERATION_MODEL` (default google/flan-t5-base)
- `CORS_ORIGINS` (default http://localhost:5173)

## Repo layout
```
interviewlens/
  backend/ (app.py, ingest.py, generate.py, rag.py, resume.py, db.py, requirements.txt)
  frontend/ (Vite React app: Upload → Role select → Interview → Summary)
  books/ (source PDFs — do NOT commit; list in README + .gitignore)
  data/ (gitignored: db, vectorstore)
  demo/ (demo video + screenshots)
  README.md, .env.example, .gitignore, resume.pdf (Sujal's resume copy)
```

## Verification (must all pass before reporting done)
1. `ingest.py` runs; chunk counts per book printed; FAISS index loads.
2. Backend boots; `/api/health` returns chunks > 0.
3. Real run with Sujal's resume (`~/workspace/user/files/AKTUIITP2_O__1__2_ncym.pdf`),
   role `ai_ml`: retrieved chunks genuinely relevant (quote 2–3 in the report),
   5 model-generated questions contextual (quote 2–3), answers stored, summary
   returned, rows present in SQLite.
4. Frontend build succeeds; full flow works against the live backend.
