"""Resume parsing: text extraction + curated skill-vocabulary matching.

No invented data: skills are only reported when the literal term (or a known
alias) appears in the resume text, matched case-insensitively.
"""
import re

from pypdf import PdfReader

# Canonical skill -> aliases matched literally in resume text.
SKILL_VOCABULARY = {
    "Python": ["python"],
    "Java": ["java"],
    "C++": ["c++"],
    "C": ["c"],
    "SQL": ["sql", "mysql", "postgresql", "sqlite"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning"],
    "Neural Networks": ["neural network"],
    "PyTorch": ["pytorch", "torch"],
    "TensorFlow": ["tensorflow"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "NLP": ["natural language processing", "nlp"],
    "Computer Vision": ["computer vision"],
    "Data Analysis": ["data analysis", "data analytics"],
    "Statistics": ["statistics", "statistical"],
    "Probability": ["probability"],
    "Linear Regression": ["linear regression"],
    "Logistic Regression": ["logistic regression"],
    "Decision Trees": ["decision tree"],
    "Random Forest": ["random forest"],
    "SVM": ["support vector machine", "svm"],
    "Clustering": ["clustering", "k-means", "kmeans"],
    "Gradient Boosting": ["gradient boosting", "xgboost", "lightgbm"],
    "Transformers": ["transformer"],
    "LLM": ["large language model", "llm"],
    "RAG": ["retrieval-augmented generation", "rag"],
    "LangChain": ["langchain"],
    "FastAPI": ["fastapi"],
    "Django": ["django"],
    "Flask": ["flask"],
    "React": ["react"],
    "JavaScript": ["javascript"],
    "HTML": ["html"],
    "CSS": ["css"],
    "Git": ["git", "github"],
    "Docker": ["docker"],
    "AWS": ["aws", "amazon web services"],
    "Data Structures": ["data structures", "data structure"],
    "Algorithms": ["algorithms", "algorithm"],
    "Data Science": ["data science"],
    "TypeScript": ["typescript"],
    "Node.js": ["node.js", "nodejs"],
    "MongoDB": ["mongodb"],
    "Data Visualization": ["data visualization", "matplotlib", "seaborn"],
    "Feature Engineering": ["feature engineering"],
    "Model Evaluation": ["model evaluation", "cross-validation", "cross validation"],
    "Reinforcement Learning": ["reinforcement learning"],
    "EDA": ["exploratory data analysis"],
    "Big Data": ["big data", "spark", "hadoop"],
}

TECHNOLOGIES = {
    "Python", "Java", "C++", "C", "SQL", "PyTorch", "TensorFlow",
    "scikit-learn", "Pandas", "NumPy", "LangChain", "FastAPI", "Django",
    "Flask", "React", "JavaScript", "TypeScript", "Node.js", "MongoDB",
    "HTML", "CSS", "Git", "Docker", "AWS",
}

# Skill -> domain bucket(s).
SKILL_DOMAINS = {
    "Machine Learning": ["machine learning"],
    "Deep Learning": ["machine learning"],
    "Neural Networks": ["machine learning"],
    "PyTorch": ["machine learning"],
    "TensorFlow": ["machine learning"],
    "scikit-learn": ["machine learning"],
    "Transformers": ["machine learning"],
    "LLM": ["machine learning"],
    "RAG": ["machine learning"],
    "LangChain": ["machine learning"],
    "NLP": ["natural language processing"],
    "Computer Vision": ["computer vision"],
    "Data Analysis": ["data science"],
    "Data Science": ["data science"],
    "Statistics": ["data science"],
    "Probability": ["data science"],
    "Data Visualization": ["data science"],
    "EDA": ["data science"],
    "Big Data": ["data science"],
    "SQL": ["data science"],
    "Feature Engineering": ["data science"],
    "Pandas": ["data science"],
    "NumPy": ["data science"],
    "FastAPI": ["backend"],
    "Django": ["backend"],
    "Flask": ["backend"],
    "React": ["frontend"],
    "JavaScript": ["frontend"],
    "HTML": ["frontend"],
    "CSS": ["frontend"],
    "Docker": ["devops"],
    "AWS": ["devops"],
    "Git": ["devops"],
}


def extract_text_from_pdf_bytes(data: bytes) -> str:
    reader = PdfReader(__import__("io").BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n".join(parts)


def extract_text_from_bytes(data: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        return extract_text_from_pdf_bytes(data)
    return data.decode("utf-8", errors="ignore")


def _matches(text_lower: str, pattern: str) -> bool:
    # Whole-word / whole-phrase match: "ml" must not match "html",
    # "rag" must not match "drag", "java" must not match "javascript".
    return re.search(
        r"(?<!\w)" + re.escape(pattern.lower()) + r"(?!\w)", text_lower
    ) is not None


def parse_resume_text(text: str) -> dict:
    text_lower = text.lower()
    skills = [
        skill
        for skill, aliases in SKILL_VOCABULARY.items()
        if any(_matches(text_lower, a) for a in aliases)
    ]
    technologies = [s for s in skills if s in TECHNOLOGIES]
    domains = sorted(
        {d for s in skills for d in SKILL_DOMAINS.get(s, [])}
    )
    # Name heuristic: first non-empty line that looks like a person name
    # (2-4 title-case words, no digits, not a section header).
    name = None
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 60 or any(ch.isdigit() for ch in line):
            continue
        if line.lower() in {
            "resume", "curriculum vitae", "cv", "profile", "education",
        }:
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(
            w[0].isupper() for w in words if w and w[0].isalpha()
        ):
            name = line
            break
    return {
        "skills": skills,
        "technologies": technologies,
        "domains": domains,
        "name": name,
    }
