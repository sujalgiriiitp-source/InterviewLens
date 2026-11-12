"""Shared constants for InterviewLens backend: roles and their book KBs."""
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
VECTORSTORE_DIR = os.environ.get(
    "VECTORSTORE_DIR", os.path.join(DATA_DIR, "vectorstore")
)
DATABASE_PATH = os.environ.get(
    "DATABASE_URL", "sqlite:///./data/interviewlens.db"
).replace("sqlite:///", "")
if not os.path.isabs(DATABASE_PATH):
    DATABASE_PATH = os.path.join(PROJECT_ROOT, DATABASE_PATH)
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
GENERATION_MODEL = os.environ.get(
    "GENERATION_MODEL", "google/flan-t5-base"
)

# Book title -> filename. Mitchell comes from OCR text when present.
BOOKS = {
    "Mitchell — Machine Learning": "mitchell-ml.pdf",
    "Burkov — The Hundred-Page Machine Learning Book": "burkov-100page-ml.pdf",
    "Bishop — Pattern Recognition and Machine Learning": "bishop-prml.pdf",
    "Brownlee — Master Machine Learning Algorithms": "brownlee-master-ml-algorithms.pdf",
    "Müller & Guido — Introduction to Machine Learning with Python": "intro-ml-python.pdf",
    "Bonaccorso — Machine Learning for Absolute Beginners": "ml-absolute-beginners.pdf",
}

ROLES = {
    "ai_ml": {
        "id": "ai_ml",
        "label": "AI/ML Engineer",
        "books": [
            "Mitchell — Machine Learning",
            "Burkov — The Hundred-Page Machine Learning Book",
            "Bishop — Pattern Recognition and Machine Learning",
            "Brownlee — Master Machine Learning Algorithms",
        ],
        "default_topics": [
            "supervised learning",
            "decision trees",
            "neural networks",
            "overfitting and generalization",
            "model evaluation",
        ],
    },
    "data_science": {
        "id": "data_science",
        "label": "Data Science / Applied ML Engineer",
        "books": [
            "Müller & Guido — Introduction to Machine Learning with Python",
            "Brownlee — Master Machine Learning Algorithms",
            "Bonaccorso — Machine Learning for Absolute Beginners",
            "Burkov — The Hundred-Page Machine Learning Book",
        ],
        "default_topics": [
            "data preprocessing",
            "supervised learning",
            "model evaluation",
            "feature engineering",
            "unsupervised learning",
        ],
    },
}
