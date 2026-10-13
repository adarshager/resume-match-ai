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
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          params={"key": os.getenv("GEMINI_API_KEY")}, timeout=90,
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseMimeType": "application/json"}})
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
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
    mode, data = "Offline keyword mode", None
    try:
        data = ai(resume, jd)
        if data:
            mode = "AI mode"
    except Exception as e:
        mode = f"Offline mode (AI error: {str(e)[:80]})"
    data = data or offline(resume, jd)
    data["mode"] = mode
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
