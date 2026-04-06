# ============================================================
# ResumeRanker - FINAL WORKING BACKEND (Single File Version)
# ============================================================

# Run:
# uvicorn main:app --reload

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pdfplumber
import spacy
import re
import io

# ============================
# INIT APP
# ============================

app = FastAPI(title="ResumeRanker API")

# ============================
# CORS
# ============================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================
# NLP MODEL
# ============================

nlp = spacy.load("en_core_web_sm")

# ============================
# SKILLS LIST
# ============================

COMMON_SKILLS = [
    "python", "java", "javascript", "c++", "c#", "typescript",
    "machine learning", "deep learning", "nlp", "computer vision",
    "sql", "mongodb", "postgresql", "mysql", "redis",
    "aws", "azure", "gcp", "docker", "kubernetes",
    "react", "node.js", "fastapi", "django", "flask",
    "git", "linux", "tensorflow", "pytorch", "pandas", "numpy",
    "data analysis", "data science", "communication", "teamwork",
    "problem solving", "leadership", "agile", "scrum"
]

# ============================
# HELPERS
# ============================

def extract_text_from_bytes(file_bytes):
    """Extract text from PDF bytes directly (no saving to disk)"""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return " ".join([p.extract_text() or "" for p in pdf.pages])
    except Exception as e:
        raise Exception(f"Could not read PDF: {str(e)}")

def parse_skills(text):
    """Extract skills found in text"""
    text_lower = text.lower()
    return [s for s in COMMON_SKILLS if s in text_lower]

def extract_job_skills(job_desc):
    """Extract required skills from job description"""
    job_lower = job_desc.lower()
    return [s for s in COMMON_SKILLS if s in job_lower]

def compute_similarity(resume_texts, job_desc):
    """Compute TF-IDF cosine similarity between resumes and job description"""
    docs = resume_texts + [job_desc]
    tfidf = TfidfVectorizer(stop_words="english").fit_transform(docs)
    return cosine_similarity(tfidf[:-1], tfidf[-1]).flatten()

# ============================
# API: RANK (Main Endpoint)
# ============================

@app.post("/rank")
async def rank(
    job_description: str = Form(...),
    resumes: list[UploadFile] = File(...)
):
    if not job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is required")

    if not resumes:
        raise HTTPException(status_code=400, detail="No resumes uploaded")

    # Step 1 — Read all resume texts
    resume_texts = []
    filenames = []

    for file in resumes:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"{file.filename} is not a PDF. Only PDF files are supported."
            )

        file_bytes = await file.read()
        try:
            text = extract_text_from_bytes(file_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        resume_texts.append(text)
        filenames.append(file.filename)

    # Step 2 — Compute similarity scores
    scores = compute_similarity(resume_texts, job_description)

    # Step 3 — Extract job skills for comparison
    job_skills = extract_job_skills(job_description)

    # Step 4 — Build results
    results = []
    for i, text in enumerate(resume_texts):
        resume_skills = parse_skills(text)
        matched = list(set(resume_skills) & set(job_skills))
        missing = list(set(job_skills) - set(resume_skills))
        score_percent = round(float(scores[i]) * 100, 1)  # Convert 0.85 → 85.0

        results.append({
            "filename": filenames[i],       # e.g. "john_doe.pdf"
            "score": score_percent,          # e.g. 85.0
            "skills": matched,               # e.g. ["python", "sql"]
            "explanation": {
                "missing_skills": missing    # e.g. ["docker", "aws"]
            }
        })

    # Step 5 — Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "total_candidates": len(results),
        "rankings": results
    }

# ============================
# ROOT
# ============================

@app.get("/")
def root():
    return {"status": "ResumeRanker Running"}

@app.get("/ping")
def ping():
    return {"message": "Backend is connected!"}