# Resume Match AI

Paste/upload a resume + a job description -> get a match score, matching skills, missing keywords,
before/after bullet suggestions and a pre-apply checklist.

## Run in VS Code
1. Open this folder in VS Code (File > Open Folder), then open a terminal (Ctrl + `).
2. Create and activate a virtual environment
   - Windows: `python -m venv .venv` then `.venv\Scripts\activate`
   - Mac/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Run `python app.py` and open http://127.0.0.1:5000

## Enable AI mode (optional)
Copy `.env.example` to `.env` and add ONE key: `ANTHROPIC_API_KEY` (Claude) or `GEMINI_API_KEY`
(free key from Google AI Studio). Without a key the app runs in offline keyword mode.

## Structure
- `app.py` - Flask server, file parsing, AI call, offline analyser
- `templates/index.html` - dashboard UI (HTML + CSS + JS)
- `docs/Project_Report.docx` - project report

Note: the UI loads Tailwind CSS and fonts from a CDN, so keep an internet connection on when you open the page.

## Deploy free on Render
1. Push this folder to a GitHub repo (`.env` is git-ignored, so keys are never uploaded).
2. On render.com choose New > Blueprint (uses `render.yaml`), or New > Web Service with
   build command `pip install -r requirements.txt` and start command `gunicorn app:app --timeout 120`.
3. Pick the Free instance and, optionally, add `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` under Environment.
   Without a key the live demo runs in offline mode, which also protects your key from public use.
4. Free services sleep after 15 minutes idle; the first request afterwards takes about a minute.
