"""Question generation with google/flan-t5-base (local, CPU).

HARD RULE: every question comes from the model prompted with retrieved
context. There is NO template fallback anywhere in this module: if the
model cannot be loaded or generation fails, raise ModelUnavailableError
and the API returns HTTP 503.
"""
import re

import torch

from config import GENERATION_MODEL

_tokenizer = None
_model = None


class ModelUnavailableError(RuntimeError):
    pass


def _load():
    global _tokenizer, _model
    if _model is None:
        try:
            torch.set_num_threads(2)
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            _tokenizer = AutoTokenizer.from_pretrained(GENERATION_MODEL)
            _model = AutoModelForSeq2SeqLM.from_pretrained(GENERATION_MODEL)
            _model.eval()
        except Exception as exc:  # noqa: BLE001 - surface as 503
            raise ModelUnavailableError(
                f"Failed to load generation model {GENERATION_MODEL}: {exc}"
            ) from exc
    return _tokenizer, _model


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.strip("\"' ")
    # Drop any leading "Question:" style prefix the model may echo.
    text = re.sub(r"^(question|q)\s*\d*\s*[:\-]\s*", "", text, flags=re.I)
    return text


BANNED_PHRASES = (
    "main topics",
    "main features",
    "of this book",
    "in the text",
    "in this text",
    "discussed in the",
    "this position",
    "skills required",
    "skills needed",
    "best book",
    "this interviewer",
    "data analyst must",
    "tell me about yourself",
    "what is the threshold?",
    "mainly about",
    "is the text",
)

# Topic grounding: a generated question must contain at least one
# content word from its topic (substring match, e.g. "overfit" matches
# "overfitting"). This is a validity filter only — the question itself
# still comes entirely from the model.
TOPIC_KEYWORDS = {
    "supervised learning": ["supervised", "label", "classification", "regression", "training", "predict"],
    "decision trees": ["tree", "split", "entropy", "gain", "leaf", "branch", "node", "decision"],
    "neural networks": ["network", "neuron", "neural", "layer", "activation", "weight", "backpropagat", "hidden"],
    "overfitting and generalization": ["overfit", "generaliz", "underfit", "bias", "variance", "regulariz", "complexity"],
    "model evaluation": ["evaluat", "accuracy", "precision", "recall", "validat", "cross", "metric", "test set"],
    "natural language processing": ["language", "text", "nlp", "token", "word", "sentence"],
    "data preprocessing": ["preprocess", "scaling", "normaliz", "missing", "clean"],
    "feature engineering": ["feature", "selection", "extraction", "engineering"],
    "unsupervised learning": ["unsupervised", "cluster", "k-means", "kmeans"],
    "computer vision": ["vision", "image", "convolutional", "pixel"],
}


def _is_valid_question(text: str, topic: str = "") -> bool:
    if not text or len(text) < 25 or len(text) > 400:
        return False
    lowered = text.lower()
    if any(p in lowered for p in BANNED_PHRASES):
        return False
    keywords = TOPIC_KEYWORDS.get(topic or "")
    if keywords and not any(k in lowered for k in keywords):
        return False
    # Must read like a question: ends with ? or starts with a question word.
    if text.endswith("?"):
        return True
    return bool(
        re.match(
            r"^(what|why|how|when|where|which|explain|describe|compare|"
            r"discuss|can you|could you|suppose|consider|given)\b",
            text,
            flags=re.I,
        )
    )


def generate_question(role_label, skills, topic, context_chunks,
                      max_new_tokens=64, temperature=0.7):
    """One model call -> one interview question, or raise ModelUnavailableError."""
    tokenizer, model = _load()
    context = "\n".join(c["text"] for c in context_chunks)[:1200]
    skill_str = ", ".join(skills) if skills else "general machine learning"
    prompt = (
        f"Textbook text:\n{context}\n\n"
        f"Example: Text about gradient descent says the learning rate "
        f"controls step size and a rate that is too large can diverge. "
        f"Question: How does the learning rate affect whether gradient "
        f"descent converges?\n\n"
        f"Now write one interview question about {topic} based on the "
        f"textbook text above. Ask exactly one specific question, no "
        f"preamble, no answer, do not mention the book or the text."
    )
    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True,
                           max_length=1024)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=True,
                top_p=0.9,
            )
        text = tokenizer.decode(out[0], skip_special_tokens=True)
    except Exception as exc:  # noqa: BLE001 - surface as 503
        raise ModelUnavailableError(f"Question generation failed: {exc}") from exc
    question = _clean(text)
    if not _is_valid_question(question, topic):
        # One retry with greedy decoding before giving up (still the model).
        try:
            with torch.no_grad():
                out = model.generate(
                    **inputs, max_new_tokens=max_new_tokens, do_sample=False
                )
            text = tokenizer.decode(out[0], skip_special_tokens=True)
        except Exception as exc:  # noqa: BLE001
            raise ModelUnavailableError(
                f"Question generation failed: {exc}"
            ) from exc
        question = _clean(text)
    if not _is_valid_question(question, topic):
        raise ModelUnavailableError(
            f"Model produced no valid question (raw output: {text!r})"
        )
    if not question.endswith("?"):
        question += "?"
    return question


def _similarity(a: str, b: str) -> float:
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def dedupe_questions(questions):
    kept = []
    for q in questions:
        if all(_similarity(q, k) < 0.6 for k in kept):
            kept.append(q)
    return kept
