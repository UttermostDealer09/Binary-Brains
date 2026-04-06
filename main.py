# ============================================================
# ResumeRanker - FINAL WORKING BACKEND (Single File Version)
# ============================================================

# Run:
# uvicorn main:app --reload

from fastapi import FastAPI, UploadFile, File, HTTPException
from pymongo import MongoClient
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from docx import Document
import pdfplumber
import spacy
import uuid
import os
import re

# ============================
# INIT APP
# ============================

app = FastAPI(title="ResumeRanker API")

# ============================
# DATABASE
# ============================

client = MongoClient("mongodb://localhost:27017/")
db = client["resumeranker"]

# ============================
# FILE STORAGE
# ============================

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================
# NLP MODEL
# ============================

nlp = spacy.load("en_core_web_sm")

# ============================
# SKILLS LIST
# ============================

COMMON_SKILLS = [
    "python", "java", "c++", "machine learning",
    "nlp", "sql", "mongodb", "aws", "docker"
]

# ============================
# FILE HANDLING
# ============================

def extract_text(file_path):
    if file_path.endswith(".pdf"):
        with pdfplumber.open(file_path) as pdf:
            return " ".join([p.extract_text() or "" for p in pdf.pages])

    elif file_path.endswith(".docx"):
        doc = Document(file_path)
        return " ".join([p.text for p in doc.paragraphs])

    else:
        raise Exception("Unsupported format")

# ============================
# PARSER
# ============================

def parse_resume(text):
    doc = nlp(text)

    name = None
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text
            break

    text_lower = text.lower()
    skills = [s for s in COMMON_SKILLS if s in text_lower]

    exp_match = re.search(r"(\d+)\+?\s+years", text_lower)
    experience = exp_match.group() if exp_match else "Not Found"

    return {
        "name": name,
        "skills": skills,
        "experience": experience
    }

# ============================
# ANALYZER
# ============================

def compute_similarity(resumes, job):
    docs = resumes + [job]
    tfidf = TfidfVectorizer(stop_words="english").fit_transform(docs)
    return cosine_similarity(tfidf[:-1], tfidf[-1]).flatten()

def explain_score(resume_skills, job_skills):
    matched = list(set(resume_skills) & set(job_skills))
    missing = list(set(job_skills) - set(resume_skills))

    return {
        "matched_skills": matched,
        "missing_skills": missing
    }

# ============================
# API: UPLOAD
# ============================

@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    uploaded = []

    for file in files:
        if not file.filename.endswith((".pdf", ".docx")):
            continue

        path = f"{UPLOAD_DIR}/{uuid.uuid4()}_{file.filename}"

        with open(path, "wb") as f:
            f.write(await file.read())

        db.resumes.insert_one({
            "file_path": path,
            "parsed_data": None,
            "text": None
        })

        uploaded.append(file.filename)

    if not uploaded:
        raise HTTPException(status_code=400, detail="No valid files uploaded")

    return {"uploaded": uploaded}

# ============================
# API: ANALYZE
# ============================

@app.post("/analyze")
def analyze():
    resumes = list(db.resumes.find())

    if not resumes:
        raise HTTPException(status_code=400, detail="No resumes found")

    for r in resumes:
        try:
            text = extract_text(r["file_path"])
            parsed = parse_resume(text)

            db.resumes.update_one(
                {"_id": r["_id"]},
                {"$set": {"parsed_data": parsed, "text": text}}
            )

        except Exception as e:
            db.resumes.update_one(
                {"_id": r["_id"]},
                {"$set": {"error": str(e)}}
            )

    return {"message": "Analysis completed"}

# ============================
# API: JOB
# ============================

@app.post("/job")
def add_job(job: dict):
    if "description" not in job or "required_skills" not in job:
        raise HTTPException(status_code=400, detail="Invalid job format")

    db.jobs.delete_many({})
    db.jobs.insert_one(job)

    return {"message": "Job saved"}

# ============================
# API: RANK
# ============================

@app.get("/rank")
def rank():
    job = db.jobs.find_one()

    if not job:
        raise HTTPException(status_code=400, detail="No job found")

    resumes = list(db.resumes.find({"parsed_data": {"$ne": None}}))

    if not resumes:
        raise HTTPException(status_code=400, detail="No analyzed resumes")

    texts = [r["text"] for r in resumes]
    scores = compute_similarity(texts, job["description"])

    results = []

    for i, r in enumerate(resumes):
        parsed = r["parsed_data"]

        results.append({
            "name": parsed.get("name"),
            "score": float(scores[i]),
            "skills": parsed.get("skills"),
            "experience": parsed.get("experience"),
            "explanation": explain_score(
                parsed.get("skills", []),
                job["required_skills"]
            )
        })

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