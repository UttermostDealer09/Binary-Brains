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
