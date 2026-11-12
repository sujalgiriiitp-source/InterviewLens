"""InterviewLens backend — FastAPI app (see API_CONTRACT.md).

Flow: resume upload + role -> parse resume -> RAG retrieval over the ML
textbook vector store -> 5 questions from google/flan-t5-base prompted with
retrieved context -> interactive Q&A persisted in SQLite -> heuristic summary.
No template-written questions: model failure returns HTTP 503.
"""
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import db  # noqa: E402
import generate  # noqa: E402
import rag  # noqa: E402
import resume as resume_mod  # noqa: E402
from config import ROLES  # noqa: E402

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

app = FastAPI(title="InterviewLens", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/api/health")
def health():
    try:
        chunks = rag.chunk_count()
    except FileNotFoundError:
        chunks = 0
    return {"status": "ok", "roles": list(ROLES.keys()), "chunks": chunks}


@app.get("/api/roles")
def roles():
    return [
        {"id": r["id"], "label": r["label"], "books": r["books"]}
        for r in ROLES.values()
    ]


def _build_queries(role_id, parsed, topics):
    # Textbook-style topical queries: the role label + bare skill name
    # ("AI/ML Engineer Python") retrieves generic front-matter, so queries
    # are built from topic phrases instead.
    topic_queries = {
        "supervised learning": "supervised learning classification regression",
        "decision trees": "decision tree splitting information gain entropy",
        "neural networks": "neural network backpropagation activation function",
        "overfitting and generalization": "overfitting generalization bias variance",
        "model evaluation": "model evaluation cross validation accuracy precision recall",
        "natural language processing": "natural language processing text classification",
        "data preprocessing": "data preprocessing feature scaling normalization",
        "feature engineering": "feature engineering selection extraction",
        "unsupervised learning": "unsupervised learning clustering k-means",
        "computer vision": "computer vision image classification convolutional neural network",
    }
    queries = [topic_queries.get(t, t) for t in topics]
    skills = parsed.get("skills", [])
    if "Python" in skills:
        queries.append("machine learning Python scikit-learn model training")
    # 3-5 queries, deduped, order preserved.
    seen, out = set(), []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:5]


def _topics_for_role(role_id, parsed):
    role = ROLES[role_id]
    skill_topic = {
        "Machine Learning": "supervised learning",
        "Deep Learning": "neural networks",
        "Neural Networks": "neural networks",
        "NLP": "natural language processing",
        "Computer Vision": "computer vision",
        "PyTorch": "neural networks",
        "TensorFlow": "neural networks",
        "Data Analysis": "data preprocessing",
        "Statistics": "model evaluation",
        "Probability": "model evaluation",
        "Clustering": "unsupervised learning",
        "Linear Regression": "supervised learning",
        "Logistic Regression": "supervised learning",
        "Decision Trees": "supervised learning",
        "Random Forest": "supervised learning",
        "SVM": "supervised learning",
        "Gradient Boosting": "supervised learning",
        "Feature Engineering": "feature engineering",
        "Model Evaluation": "model evaluation",
        "Transformers": "neural networks",
        "LLM": "natural language processing",
        "RAG": "natural language processing",
    }
    topics = []
    for skill in parsed.get("skills", []):
        t = skill_topic.get(skill)
        if t and t not in topics:
            topics.append(t)
    for t in role["default_topics"]:
        if t not in topics:
            topics.append(t)
    return topics[:5]


@app.post("/api/sessions")
async def create_session(resume: UploadFile = File(...), role: str = Form(...)):
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Unknown role: {role}")
    if not resume.filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(
            status_code=400, detail="Resume must be a .pdf or .txt file"
        )
    data = await resume.read()
    try:
        text = resume_mod.extract_text_from_bytes(data, resume.filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse resume: {exc}")
    if len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Resume text is empty or unreadable")
    parsed = resume_mod.parse_resume_text(text)
    role_info = ROLES[role]
    topics = _topics_for_role(role, parsed)
    queries = _build_queries(role, parsed, topics)
    try:
        retrieved = rag.retrieve_multi(queries, role_info["books"], top_k=3)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not retrieved:
        raise HTTPException(
            status_code=503, detail="No relevant textbook chunks retrieved"
        )

    # Generate 5 model questions, rotating retrieved chunk pairs.
    # A generation that yields no valid question is retried with a
    # different chunk pair; only a model-load failure aborts at once.
    questions, attempts = [], 0
    while len(questions) < 5 and attempts < 12:
        i = attempts % max(1, len(retrieved))
        # One chunk per attempt: a single focused passage keeps the
        # small model on-topic better than two concatenated passages.
        pair = [retrieved[i]]
        topic = topics[attempts % len(topics)] if topics else role_info["default_topics"][0]
        try:
            qtext = generate.generate_question(
                role_info["label"], parsed.get("skills", []), topic, pair
            )
        except generate.ModelUnavailableError as exc:
            if "Failed to load" in str(exc):
                raise HTTPException(status_code=503, detail=str(exc))
            attempts += 1
            continue
        attempts += 1
        if all(generate._similarity(qtext, q["text"]) < 0.6 for q in questions):
            questions.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "text": qtext,
                    "topic": topic,
                    "source": pair[0]["source"],
                }
            )
    if len(questions) < 5:
        raise HTTPException(
            status_code=503,
            detail=f"Model produced only {len(questions)} unique questions",
        )

    session_id = str(uuid.uuid4())
    db.create_session(session_id, role, parsed, topics)
    db.add_questions(session_id, questions)
    return {
        "session_id": session_id,
        "parsed": parsed,
        "topics": topics,
        "retrieved_chunks": [
            {"source": c["source"], "page": c.get("page"), "text": c["text"]}
            for c in retrieved
        ],
        "questions": questions,
    }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


class AnswerIn(BaseModel):
    question_id: str
    answer: str


@app.post("/api/sessions/{session_id}/answers")
def submit_answer(session_id: str, payload: AnswerIn):
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not db.question_belongs_to_session(payload.question_id, session_id):
        raise HTTPException(status_code=404, detail="Question not found in session")
    if not payload.answer or not payload.answer.strip():
        raise HTTPException(status_code=400, detail="Answer must not be empty")
    db.save_answer(session_id, payload.question_id, payload.answer.strip())
    updated = db.get_session(session_id)
    next_q = next(
        (q for q in updated["questions"] if not q.get("answer")), None
    )
    return {"ok": True, "next_question": next_q}


def _compute_summary(session):
    questions = session["questions"]
    answered = [q for q in questions if q.get("answer")]
    topics_covered = sorted({q["topic"] for q in answered if q.get("topic")})
    strengths, gaps = [], []
    try:
        _, chunks = rag.load_store()
    except FileNotFoundError:
        chunks = []
    chunk_by_source = {}
    for c in chunks:
        chunk_by_source.setdefault(c["source"], []).append(c["text"])
    for q in answered:
        ans_tokens = set(re.findall(r"[a-z0-9]+", q["answer"].lower()))
        src_text = " ".join(chunk_by_source.get(q.get("source", ""), []))[:4000]
        src_tokens = set(re.findall(r"[a-z0-9]+", src_text.lower()))
        overlap = len(ans_tokens & src_tokens)
        # Basic heuristic only: answer length + keyword overlap with the
        # source textbook chunk. Not a score, not a judgement of correctness.
        if len(q["answer"]) >= 120 and overlap >= 5:
            strengths.append(q["topic"])
        elif len(q["answer"]) < 60 or overlap < 2:
            gaps.append(q["topic"])
    strengths = sorted(set(strengths))
    gaps = sorted(set(gaps))
    overall = (
        f"Answered {len(answered)} of {len(questions)} questions across "
        f"{len(topics_covered)} topic(s). "
        + (
            f"Longer, on-topic answers appeared for: {', '.join(strengths)}. "
            if strengths else ""
        )
        + (
            f"Shorter or off-topic answers appeared for: {', '.join(gaps)}. "
            if gaps else ""
        )
        + "(Basic heuristic based on answer length and keyword overlap with "
        "the source textbook material — not a score.)"
    )
    return {
        "questions_asked": len(questions),
        "answered": len(answered),
        "topics_covered": topics_covered,
        "strengths": strengths,
        "gaps": gaps,
        "overall": overall,
    }


@app.post("/api/sessions/{session_id}/finish")
def finish_session(session_id: str):
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = _compute_summary(session)
    db.set_summary(session_id, summary)
    return {"summary": summary}


@app.get("/api/sessions/{session_id}/summary")
def get_summary(session_id: str):
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("summary"):
        return {"summary": session["summary"]}
    return {"summary": _compute_summary(session)}
