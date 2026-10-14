"""Resume Match AI - analyses a resume against a job description.
AI mode  : Claude or Gemini (set a key in .env)
Offline  : keyword-based analysis, works with no API key."""
import os, re, json
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

PROMPT = """You are an expert technical recruiter and ATS specialist.
Analyse how well the resume matches the job description.
Do NOT invent any experience, skills or achievements.
Reply with ONLY valid JSON (no markdown) in exactly this shape:
{"score": <integer 0-100>,
 "matching_skills": ["..."],
 "missing_keywords": ["..."],
 "bullets": [{"original": "...", "improved": "..."}],
 "improvements": ["..."],
 "top_changes": ["exactly 5 items"]}

RESUME:
<<R>>

JOB DESCRIPTION:
<<J>>"""

SKILLS = ("python,java,javascript,typescript,c++,c#,sql,mysql,postgresql,mongodb,react,angular,node.js,"
          "flask,django,spring boot,html,css,git,github,docker,kubernetes,aws,azure,gcp,rest api,linux,"
          "agile,scrum,machine learning,deep learning,nlp,pandas,numpy,tensorflow,pytorch,data structures,"
          "algorithms,oop,unit testing,ci/cd,jira,excel,power bi,tableau,communication,teamwork,problem solving"
          ).split(",")


def has(term, text):
    return re.search(r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#])", text, re.I)


def read_file(f):
    name = f.filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(f.stream).pages)
    if name.endswith(".docx"):
        import docx
        return "\n".join(p.text for p in docx.Document(f.stream).paragraphs)
    return f.read().decode("utf-8", "ignore")


def offline(resume, jd):
    need = [s for s in SKILLS if has(s, jd)]
    have = [s for s in need if has(s, resume)]
    miss = [s for s in need if s not in have]
    score = round(100 * len(have) / len(need)) if need else 0
    pat = r"^\s*[-•*●▪–]\s*\S"
    lines = [re.sub(r"^\s*[-•*●▪–]\s*", "", l).strip() for l in resume.splitlines() if re.match(pat, l)]
    bullets = [{"original": l,
                "improved": "Start with a strong action verb and add a real, measurable result (%, users, time saved): " + l}
               for l in lines if not re.search(r"\d", l)][:4]
    tips = ["Quantify achievements with real numbers wherever you can.",
            "Mirror the job description's wording for skills you genuinely have.",
            "Keep it to one page with clear Skills, Projects and Education sections.",
            "Put the most relevant projects and skills at the top."]
    top = ([f"Add these only if you truly have the skill: {', '.join(miss[:6])}."] if miss else []) + tips
    return {"score": score, "matching_skills": have, "missing_keywords": miss, "bullets": bullets,
            "improvements": tips + ["Add an AI key in .env for deeper, context-aware rewrites."],
            "top_changes": top[:5]}


_GEMINI = "https://generativelanguage.googleapis.com/v1beta/"
_model_cache = []


def _err(r):
    try:
        return r.json()["error"]["message"]
    except Exception:
        return f"HTTP {r.status_code}"


def gemini(prompt):
    """Call Gemini with the key in a header. Picks an available Flash model automatically."""
    key = os.getenv("GEMINI_API_KEY", "").strip().strip("\"'")
    h = {"x-goog-api-key": key, "Content-Type": "application/json"}
    models = [os.getenv("GEMINI_MODEL", "").strip()]
    if not _model_cache:
        try:
            r = requests.get(_GEMINI + "models", headers=h, params={"pageSize": 100}, timeout=20)
            if r.ok:
                names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                         if "generateContent" in m.get("supportedGenerationMethods", [])]
                good = [n for n in names if "flash" in n and not re.search(r"lite|image|tts|live|audio|preview|exp|8b", n)]
                _model_cache.extend(sorted(good, reverse=True)[:3])
            elif "key" in _err(r).lower():
                raise RuntimeError(_err(r))
        except requests.RequestException:
            pass
    models += _model_cache + ["gemini-2.5-flash", "gemini-flash-latest"]
    last = "No Gemini model available"
    for m in dict.fromkeys(x for x in models if x):
        for cfg in ({"responseMimeType": "application/json"}, {}):
            r = requests.post(_GEMINI + f"models/{m}:generateContent", headers=h, timeout=90,
                              json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg})
            if r.ok:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            last = _err(r)
            if "api key" in last.lower() or r.status_code in (401, 403):
                raise RuntimeError(last)
            if r.status_code != 400:
                break
    raise RuntimeError(last)


def ai(resume, jd):
    prompt = PROMPT.replace("<<R>>", resume[:12000]).replace("<<J>>", jd[:8000])
    if os.getenv("ANTHROPIC_API_KEY"):
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=90,
                          headers={"x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                                   "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), "max_tokens": 2000,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
    elif os.getenv("GEMINI_API_KEY"):
        text = gemini(prompt)
    else:
        return None
    return json.loads(re.search(r"\{.*\}", text, re.S).group())


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/analyze")
def analyze():
    resume, jd = request.form.get("resume", ""), request.form.get("jd", "")
    f = request.files.get("file")
    if f and f.filename:
        resume = read_file(f)
    if len(resume.strip()) < 50 or len(jd.strip()) < 50:
        return jsonify(error="Please provide a resume and a job description (at least 50 characters each)."), 400
    err = ""
    mode, data = "Offline keyword mode", None
    try:
        data = ai(resume, jd)
        if data:
            mode = "AI mode"
    except Exception as e:
        app.logger.warning("AI call failed: %s", e)
        mode, err = "Offline keyword mode (AI unavailable)", str(e)[:200]
    data = data or offline(resume, jd)
    data["mode"] = mode
    data["ai_error"] = err
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
