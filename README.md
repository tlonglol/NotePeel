# NotePeel

### 🔗 Live demo → **[notepeel.xyz](https://notepeel.xyz)**
No sign-up required — just click **"Try the live demo"** to explore a sample account instantly.

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

## Features

- **Layout-aware OCR** — Google Gemini vision transcribes handwritten notes into structured HTML, preserving headers, bullet lists, multi-column layouts, and boxed/circled callouts. Math is transcribed to LaTeX and rendered with KaTeX.
- **3-pass OCR fallback** — retries on a normalized image and a lighter model to recover text from low-quality scans; HEIC photos are auto-converted to JPEG.
- **Presigned direct-to-S3 uploads** — images upload straight to S3 (bypassing the serverless request-size limit); multi-page notes merge into a single document.
- **AI flashcards** — auto-generate study flashcards from any note, with an interactive study mode (know/learning tracking, shuffle, results).
- **AI summaries & explanations** — summarize a note, or highlight any text to get a detailed explanation. Notes are auto-categorized by subject/topic/tags on upload.
- **Notebooks, search & sharing** — organize notes into color-coded notebooks, search by content/subject/topic/tags, and generate public read-only share links.
- **Auth** — email/password (JWT + bcrypt) or Google sign-in.
- **One-click demo mode** — explore a seeded sample account with zero sign-up.
- **Polish** — dark mode, rich-text editor, PDF/TXT/HTML export, and note reprocessing with side-by-side comparison before applying.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, KaTeX |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy |
| Database | PostgreSQL — Neon (serverless, pooled) |
| OCR | Google Gemini (vision) |
| AI features | Cloudflare Workers AI (Llama 3.3 70B) |
| Auth | JWT + bcrypt, Google OAuth 2.0 |
| Object storage | AWS S3 (presigned uploads) |
| Deployment | AWS Lambda (Function URL + Mangum), S3 + CloudFront, Route 53 + ACM |
| Infrastructure | Terraform (IaC), EventBridge |
| Local dev | Docker, Docker Compose |
| CI/CD | GitHub Actions |

## Architecture

Deployed as a fully serverless stack on AWS, provisioned entirely with Terraform:

```
                       notepeel.xyz  (Route 53 + ACM/TLS)
                               │
            ┌──────────────────┴───────────────────┐
            ▼                                       ▼
     CloudFront ── S3                        Lambda Function URL
  (React static build)                      (FastAPI via Mangum)
                                                    │
                   ┌──────────────┬─────────────────┼─────────────────┐
                   ▼              ▼                  ▼                 ▼
             Neon Postgres   S3 (images,      Google Gemini    Cloudflare
              (pooled)        presigned)          (OCR)         Workers AI
                                                              (Llama 3.3 70B)

     EventBridge ──(5-min keep-warm ping)──▶ Lambda
```

- **Frontend** — React/Vite build served as static files from S3 through CloudFront.
- **Backend** — FastAPI wrapped with Mangum on a single Lambda behind a Function URL; no VPC, no load balancer, no NAT gateway.
- **Database** — Neon serverless Postgres over its pooled endpoint (scales to zero).
- **Storage** — images upload directly to S3 via presigned URLs and are served back with presigned GETs.
- **AI** — Gemini does OCR; Cloudflare Workers AI (Llama 3.3) powers flashcards, summaries, explanations, and categorization.
- Idles at roughly **$0/month** thanks to the scale-to-zero serverless design.

## API

### Auth — `/api/auth`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/register` | Create account |
| POST | `/login` | Email/password login |
| POST | `/google` | Google OAuth login |
| GET | `/me` | Current user |

### Notes — `/api/notes`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/upload-url` | Get presigned S3 upload URL(s) |
| POST | `/process` | Run OCR on uploaded image(s) and create the note |
| POST | `/upload-multi` | Direct upload of multiple images, merged into one note |
| GET | `/` | List notes |
| GET | `/search` | Search by text, subject, topic, or tags |
| GET | `/categories` | List subjects / topics / tags |
| GET | `/{id}` | Get a note |
| GET | `/{id}/full` | Get a note with its image |
| PUT | `/{id}` | Update a note |
| DELETE | `/{id}` | Delete a note |
| POST | `/{id}/share` | Create a public share link |
| DELETE | `/{id}/share` | Revoke the share link |
| GET | `/shared/{token}` | View a shared note (no auth) |
| POST | `/{id}/reprocess` | Re-run OCR on the stored image |

### Notebooks — `/api/notebooks`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/` | Create a notebook |
| GET | `/` | List notebooks |
| GET | `/{id}` | Get a notebook with its notes |
| PUT | `/{id}` | Update a notebook |
| DELETE | `/{id}` | Delete a notebook |
| POST | `/{id}/notes` | Add a note to a notebook |
| DELETE | `/{id}/notes/{note_id}` | Remove a note from a notebook |

### AI — `/api/ai`
| Method | Endpoint | Description |
|---|---|---|
| POST | `/flashcards/{note_id}` | Generate flashcards |
| GET | `/flashcards/{note_id}` | Get cached flashcards |
| POST | `/summarize/{note_id}` | Generate a summary |
| POST | `/explain` | Explain highlighted text |
| GET | `/explanations/{note_id}` | Get saved explanations |
| POST | `/categorize/{note_id}` | Auto-categorize a note |

## Local development

### Docker (recommended)
```bash
cp backend/.env.example backend/.env   # then fill in your keys
docker compose up --build
```
Backend runs at `http://localhost:8000`, frontend at `http://localhost:5173`.

### Manual

**Backend** — `backend/.env`:
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/notepeel
SECRET_KEY=change-me                 # JWT signing
GEMINI_API_KEY=...                   # OCR (required)
CF_ACCOUNT_ID=...                    # Cloudflare Workers AI
CF_API_TOKEN=...
S3_BUCKET_NAME=...                   # image storage (AWS S3, or any S3-compatible bucket)
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=...                 # omit on AWS if the Lambda uses an IAM role
S3_SECRET_ACCESS_KEY=...
# S3_ENDPOINT=...                    # only for S3-compatible providers
GOOGLE_CLIENT_ID=...                 # optional, for Google sign-in
```
```bash
cd backend
pip install -r requirements.txt
python -m scripts.migrate            # create tables
uvicorn main:app --reload
```

**Frontend** — `frontend/.env`:
```bash
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=your-google-client-id   # optional
```
```bash
cd frontend
npm install
npm run dev
```

## Deployment (AWS, via Terraform)

All infrastructure lives in `infra/` as code (Lambda, S3, CloudFront, Route 53, ACM, EventBridge, IAM).

```bash
# 1. Build the backend Lambda package (Linux wheels)
cd backend && ./build.sh

# 2. Provision (fill infra/terraform.tfvars with your secrets first)
cd ../infra && terraform init && terraform apply

# 3. Create the database tables in Neon
cd ../backend && DATABASE_URL="<neon-pooled-url>" python -m scripts.migrate

# 4. Build and publish the frontend
cd ../frontend
VITE_API_URL="$(terraform -chdir=../infra output -raw function_url)" npm run build
aws s3 sync dist/ "s3://$(terraform -chdir=../infra output -raw frontend_bucket)" --delete
```

Seed the public demo account any time with `python -m scripts.seed_demo`.

## Team

Built by Edwin Morales Jr, Karim Elneshili, and Tyler Long at SUNY New Paltz.
