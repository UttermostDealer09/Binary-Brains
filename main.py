# main.py

from fastapi import FastAPI
from routes import upload, analyze, job, rank
from utils.database import connect_db

app = FastAPI(title="ResumeRanker API")

connect_db()

app.include_router(upload.router)
app.include_router(analyze.router)
app.include_router(job.router)
app.include_router(rank.router)

@app.get("/")
def root():
    return {"status": "ResumeRanker Running"}
# utils/database.py

from pymongo import MongoClient

client = None
db = None

def connect_db():
    global client, db
    client = MongoClient("mongodb://localhost:27017/")
    db = client["resumeranker"]

def get_db():
    return db
# utils/file_handler.py

import pdfplumber
from docx import Document

def extract_text(file_path):
    if file_path.endswith(".pdf"):
        with pdfplumber.open(file_path) as pdf:
            return " ".join([p.extract_text() or "" for p in pdf.pages])

    elif file_path.endswith(".docx"):
        doc = Document(file_path)
        return " ".join([p.text for p in doc.paragraphs])

    else:
        raise Exception("Unsupported format")
    # services/parser.py

import spacy
import re

nlp = spacy.load("en_core_web_sm")

COMMON_SKILLS = [
    "python", "java", "c++", "machine learning",
    "nlp", "sql", "mongodb", "aws", "docker"
]

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
# services/analyzer.py

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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
# routes/upload.py

from fastapi import APIRouter, UploadFile, File
import uuid, os
from utils.database import get_db

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    db = get_db()
    uploaded = []

    for file in files:
        if not file.filename.endswith((".pdf", ".docx")):
            continue

        path = f"{UPLOAD_DIR}/{uuid.uuid4()}_{file.filename}"

        with open(path, "wb") as f:
            f.write(await file.read())

        db.resumes.insert_one({"file_path": path})
        uploaded.append(file.filename)

    return {"uploaded": uploaded}
# routes/analyze.py

from fastapi import APIRouter
from utils.database import get_db
from utils.file_handler import extract_text
#from services.parser import parse_resume

router = APIRouter()

@router.post("/analyze")
def analyze():
    db = get_db()

    for r in db.resumes.find():
        text = extract_text(r["file_path"])
        parsed = parse_resume(text)

        db.resumes.update_one(
            {"_id": r["_id"]},
            {"$set": {"parsed_data": parsed, "text": text}}
        )

    return {"message": "Analyzed"}
# routes/rank.py

from fastapi import APIRouter
from utils.database import get_db
from services.analyzer import compute_similarity, explain_score

router = APIRouter()

@router.get("/rank")
def rank():
    db = get_db()

    job = db.jobs.find_one()
    resumes = list(db.resumes.find({"parsed_data": {"$ne": None}}))

    texts = [r["text"] for r in resumes]
    scores = compute_similarity(texts, job["description"])

    results = []

    for i, r in enumerate(resumes):
        parsed = r["parsed_data"]

        results.append({
            "name": parsed["name"],
            "score": float(scores[i]),
            "explanation": explain_score(
                parsed["skills"],
                job["required_skills"]
            )
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return {"rankings": results}