# NotePeel

A full-stack AI-powered note digitization platform that converts handwritten notes into structured, editable documents with built-in study tools.

Upload a photo of your handwritten notes and get back a clean, formatted digital version that preserves the original layout. Then use AI to generate flashcards, summaries, and explanations to study from your notes.

## Screenshots

| Login | Notebooks |
|---|---|
| ![Login](screenshots/login.png) | ![Notebooks](screenshots/notebooks.png) |

| Dashboard | Dark Mode |
|---|---|
| ![Dashboard](screenshots/dashboard.png) | ![Dark Mode](screenshots/darkmode.png) |

| Flashcards (Question) | Flashcards (Answer) |
|---|---|
| ![Flashcards](screenshots/flashcards.png) | ![Flashcards Answer](screenshots/flashcards_answer.png) |

| AI Summary |
|---|
| ![Summary](screenshots/summary.png) |

## Live Features

- **OCR with layout preservation** — converts handwritten notes into structured HTML, preserving headers, bullet lists, columns, boxed sections, and diagrams
- **Multi-page batch upload** — upload multiple images at once and merge them into a single note
- **AI flashcard generation** — auto-generate study flashcards from any note, with an interactive study mode (know/learning tracking, shuffle, results)
- **AI summaries** — generate concise summaries of note content
- **AI text explanation** — highlight any text in a note and get a detailed explanation
- **Notebooks** — organize notes into color-coded notebooks
- **Search and filter** — search notes by content, subject, topic, or tags
- **Share via link** — generate public read-only links to share notes with anyone
- **Google OAuth** — sign in with Google or traditional email/password
- **Dark mode** — full dark mode with persistent preference
- **Rich text editor** — bold, italic, underline, highlights, lists, colors, and more
- **Export** — download notes as PDF, TXT, or HTML
- **Note reprocessing** — re-run OCR with side-by-side comparison before applying changes

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite |
| Backend | Python, FastAPI |
| Database | PostgreSQL, SQLAlchemy |
| AI | Cloudflare Workers AI (Llama 3.3 70B), Google Gemini |
| Auth | JWT + bcrypt, Google OAuth 2.0 |
| Storage | Cloudflare R2 |
| Containerization | Docker, Docker Compose |

## Architecture

```
┌──────────────────────────────────────────────────┐
│           React Frontend (TypeScript/Vite)        │
│  Auth  │  Notebooks  │  Editor  │  AI Tools      │
└────────────────────┬─────────────────────────────┘
                     │ REST API
┌────────────────────▼─────────────────────────────┐
│             FastAPI Backend (Python)              │
│  Auth  │  Notes  │  Notebooks  │  AI  │  OCR     │
└────┬─────────┬──────────┬────────────┬───────────┘
     │         │          │            │
┌────▼───┐ ┌───▼────┐ ┌───▼──────┐ ┌──▼──────────┐
│Postgres│ │  R2    │ │ Workers  │ │   Gemini    │
│  (DB)  │ │(Images)│ │   AI     │ │   (OCR)     │
└────────┘ └────────┘ └──────────┘ └─────────────┘
```

## API Endpoints

### Auth — `/api/auth`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Login with email/password |
| POST | `/api/auth/google` | Login with Google OAuth |
| GET | `/api/auth/me` | Get current user |

### Notes — `/api/notes`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/notes/upload` | Upload image and run OCR |
| POST | `/api/notes/upload-batch` | Upload multiple images, merge into one note |
| GET | `/api/notes/` | List all notes |
| GET | `/api/notes/{id}` | Get note |
| GET | `/api/notes/{id}/full` | Get note with original image |
| PUT | `/api/notes/{id}` | Update note |
| DELETE | `/api/notes/{id}` | Delete note |
| POST | `/api/notes/{id}/share` | Generate public share link |
| DELETE | `/api/notes/{id}/share` | Revoke share link |
| GET | `/api/notes/shared/{token}` | View shared note (no auth) |
| POST | `/api/notes/{id}/reprocess` | Re-run OCR on existing note |

### Notebooks — `/api/notebooks`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/notebooks/` | Create notebook |
| GET | `/api/notebooks/` | List notebooks |
| PUT | `/api/notebooks/{id}` | Update notebook |
| DELETE | `/api/notebooks/{id}` | Delete notebook |
| POST | `/api/notebooks/{id}/notes/{note_id}` | Add note to notebook |
| DELETE | `/api/notebooks/{id}/notes/{note_id}` | Remove note from notebook |

### AI — `/api/ai`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ai/flashcards/{note_id}` | Generate flashcards |
| GET | `/api/ai/flashcards/{note_id}` | Get cached flashcards |
| POST | `/api/ai/summarize/{note_id}` | Generate summary |
| POST | `/api/ai/explain` | Explain highlighted text |
| POST | `/api/ai/categorize/{note_id}` | Auto-categorize note |

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt

# Create .env
DATABASE_URL=postgresql://user:pass@localhost:5432/notepeel
GEMINI_API_KEY=your_key
GOOGLE_CLIENT_ID=your_google_client_id
R2_ENDPOINT=your_r2_endpoint
R2_ACCESS_KEY_ID=your_key
R2_SECRET_ACCESS_KEY=your_secret
R2_BUCKET_NAME=your_bucket
CF_ACCOUNT_ID=your_cf_account
CF_API_TOKEN=your_cf_token

uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install

# Create .env
VITE_GOOGLE_CLIENT_ID=your_google_client_id

npm run dev
```

## Team

Built by Edwin Morales Jr, Karim Elneshili, and Tyler Long at SUNY New Paltz.
