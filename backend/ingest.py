"""RAG ingestion: books/*.pdf (+ books/mitchell-ocr.txt) -> FAISS + chunks.json.

Chunking: ~800 chars with 150-char overlap, split on paragraph boundaries
where possible; keeps `source` (book title) + `page` metadata.
Embeddings: sentence-transformers/all-MiniLM-L6-v2 (local, CPU).
Store: FAISS IndexFlatIP on L2-normalised embeddings + chunks.json.
Prints chunk counts per book; exits non-zero if total chunks == 0.

Mitchell is a scanned PDF with no text layer: it is ingested from
books/mitchell-ocr.txt when present, otherwise skipped with a log line.
ai-ml-dl.pdf is an HTML error page, not a book, and is ignored.
"""
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BOOKS, EMBEDDING_MODEL, PROJECT_ROOT, VECTORSTORE_DIR  # noqa: E402

BOOKS_DIR = os.path.join(PROJECT_ROOT, "books")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
MIN_PAGE_CHARS = 40

SKIP_FILES = {"ai-ml-dl.pdf", "mitchell-ml.pdf"}  # error page; scanned (OCR only)


def _is_junk_chunk(text: str) -> bool:
    """Drop table-of-contents / index / front-matter chunks.

    TOC chunks are full of dot leaders and page numbers and carry no
    teachable content; retrieving them makes the model ask questions
    about the book instead of about ML.
    """
    if text.count("....") >= 2:
        return True
    if len(text) > 0 and sum(c.isdigit() for c in text) / len(text) > 0.15:
        return True
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 4:
        page_no_lines = sum(
            1 for ln in lines
            if len(ln.strip()) < 90 and re.search(r"\d{1,4}\s*$", ln.strip())
        )
        if page_no_lines / len(lines) > 0.4:
            return True
    return False


def chunk_text(text, source, page):
    """Split text into ~800-char chunks with 150-char overlap.

    Splits on paragraph boundaries where possible; long paragraphs are
    hard-split. The overlap is the tail of the previous chunk.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        while para:
            room = CHUNK_SIZE - len(current)
            if len(para) <= room:
                current = (current + "\n\n" + para).strip() if current else para
                para = ""
            else:
                if current:
                    # Fill current up to CHUNK_SIZE with the head of para.
                    take = para[:room].rsplit(" ", 1)[0] if " " in para[:room] else para[:room]
                    current = (current + " " + take).strip()
                    para = para[len(take):].strip()
                    chunks.append({"source": source, "page": page, "text": current})
                    current = current[-CHUNK_OVERLAP:] if len(current) > CHUNK_OVERLAP else ""
                else:
                    take = para[:CHUNK_SIZE]
                    chunks.append({"source": source, "page": page, "text": take})
                    para = para[CHUNK_SIZE:].strip()
                    current = ""
    if current.strip():
        chunks.append({"source": source, "page": page, "text": current.strip()})
    return [c for c in chunks if len(c["text"]) >= 80]


def extract_pdf(path, source):
    """Extract (page_no, text) pairs with pypdf; skip near-empty pages."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"[ \t]+", " ", text)
        if len(text.strip()) >= MIN_PAGE_CHARS:
            pages.append((i, text))
    return pages


def extract_mitchell_ocr(path, source):
    """Parse books/mitchell-ocr.txt; page markers look like [[PAGE 12]]."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    parts = re.split(r"\[\[PAGE\s+(\d+)\]\]", raw)
    pages = []
    if len(parts) > 1:
        for i in range(1, len(parts), 2):
            page_no = int(parts[i])
            text = parts[i + 1]
            if len(text.strip()) >= MIN_PAGE_CHARS:
                pages.append((page_no, text))
    else:
        # No markers: treat whole file as one block, page unknown.
        if len(raw.strip()) >= MIN_PAGE_CHARS:
            pages.append((None, raw))
    return pages


def ingest():
    per_book = {}
    all_chunks = []
    for title, filename in BOOKS.items():
        path = os.path.join(BOOKS_DIR, filename)
        if filename == "mitchell-ml.pdf":
            ocr_path = os.path.join(BOOKS_DIR, "mitchell-ocr.txt")
            if os.path.exists(ocr_path):
                pages = extract_mitchell_ocr(ocr_path, title)
                print(f"[ingest] Mitchell: using OCR text ({len(pages)} pages)")
            else:
                print("[ingest] Mitchell: SKIPPED — scanned PDF, no OCR text "
                      "(books/mitchell-ocr.txt not present)")
                per_book[title] = 0
                continue
        elif filename in SKIP_FILES:
            print(f"[ingest] {title}: SKIPPED ({filename} not a usable book)")
            per_book[title] = 0
            continue
        elif not os.path.exists(path):
            print(f"[ingest] {title}: SKIPPED — file not found: {filename}")
            per_book[title] = 0
            continue
        else:
            pages = extract_pdf(path, title)
        book_chunks = []
        for page_no, text in pages:
            book_chunks.extend(chunk_text(text, title, page_no))
        kept = [c for c in book_chunks if not _is_junk_chunk(c["text"])]
        dropped = len(book_chunks) - len(kept)
        if dropped:
            print(f"[ingest] {title}: dropped {dropped} TOC/front-matter chunks")
        book_chunks = kept
        per_book[title] = len(book_chunks)
        all_chunks.extend(book_chunks)
        print(f"[ingest] {title}: {len(pages)} pages -> {len(book_chunks)} chunks")

    total = len(all_chunks)
    print(f"[ingest] TOTAL chunks: {total}")
    if total == 0:
        print("[ingest] ERROR: no chunks produced", file=sys.stderr)
        return 1

    print(f"[ingest] Embedding {total} chunks with {EMBEDDING_MODEL} ...")
    import torch

    torch.set_num_threads(2)
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(
        texts, batch_size=32, normalize_embeddings=True, show_progress_bar=True
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    import faiss

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    os.makedirs(VECTORSTORE_DIR, exist_ok=True)
    faiss.write_index(index, os.path.join(VECTORSTORE_DIR, "index.faiss"))
    with open(os.path.join(VECTORSTORE_DIR, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False)
    print(f"[ingest] Wrote index + {total} chunks to {VECTORSTORE_DIR}")
    print("[ingest] Chunk counts per book:")
    for title, count in per_book.items():
        print(f"  {title}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(ingest())
