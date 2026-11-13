import hashlib
import math
import re
import secrets
import sqlite3
import time
from pathlib import Path

import chromadb

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "chroma_db"
ACCESS_DB = BASE_DIR / "access_codes.sqlite3"
chroma_client = chromadb.PersistentClient(path=str(DB_DIR))
collection = chroma_client.get_or_create_collection(name="medical_records", metadata={"hnsw:space": "cosine"})


def create_embedding(text, dimensions=384):
    words = re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())
    features = words + [f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)]
    vector = [0.0] * dimensions
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dimensions] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def store_document(text, patient_id, document_id):
    text = text.strip()
    if not text:
        return 0
    safe_id = hashlib.sha256(document_id.encode("utf-8")).hexdigest()[:16]
    chunks = [text[i:i + 900].strip() for i in range(0, len(text), 750)]
    chunks = [chunk for chunk in chunks if chunk]
    collection.delete(where={"$and": [{"patient_id": patient_id}, {"document_key": safe_id}]})
    collection.upsert(
        ids=[f"{patient_id}_{safe_id}_{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=[create_embedding(chunk) for chunk in chunks],
        metadatas=[{"patient_id": patient_id, "document_id": document_id, "document_key": safe_id, "chunk_index": i} for i in range(len(chunks))],
    )
    return len(chunks)


def search_records(question, patient_id, limit=5):
    if not question.strip() or collection.count() == 0:
        return []
    results = collection.query(query_embeddings=[create_embedding(question)], n_results=min(limit, collection.count()), where={"patient_id": patient_id}, include=["documents", "metadatas", "distances"])
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    return [{"text": d, "document_id": m.get("document_id", "Unknown record"), "distance": x} for d, m, x in zip(docs, metas, distances)]


def generate_answer(question, patient_id):
    records = search_records(question, patient_id)
    if not records:
        return "No matching information found in this patient's records."
    q = question.lower()
    patterns = [
        (("allergy", "allergic"), r"(?:Recorded allergy|Allerg(?:y|ies))\s*:?\s*([^\n.;]+)", "Recorded allergy"),
        (("blood pressure", "bp"), r"Blood pressure\s*:?[ \t]*([0-9]+\s*/\s*[0-9]+\s*mmHg)", "Blood pressure"),
        (("glucose", "sugar"), r"(?:Fasting blood glucose|Glucose)\s*:?[ \t]*([0-9.]+\s*mg/dL)", "Fasting blood glucose"),
        (("cholesterol",), r"Total cholesterol\s*:?[ \t]*([0-9.]+\s*mg/dL)", "Total cholesterol"),
        (("haemoglobin", "hemoglobin"), r"Ha?emoglobin\s*:?[ \t]*([0-9.]+\s*g/dL)", "Haemoglobin"),
        (("heart attack", "cardiac event"), r"heart attack.*?in\s+(\d{4})", "Previous heart attack recorded in"),
    ]
    for terms, pattern, label in patterns:
        if any(term in q for term in terms):
            for record in records:
                match = re.search(pattern, record["text"], re.I | re.S)
                if match:
                    return f"{label}: {match.group(1).strip()}"
    excerpt = re.sub(r"\s+", " ", records[0]["text"]).strip()
    if len(excerpt) > 500:
        excerpt = excerpt[:497].rsplit(" ", 1)[0] + "..."
    return f"Relevant record excerpt: {excerpt}"


def list_patient_documents(patient_id):
    result = collection.get(where={"patient_id": patient_id}, include=["metadatas"])
    # Legacy uploads may have more than one internal key for the same filename.
    names = {
        meta.get("document_id", "Unknown record")
        for meta in result.get("metadatas") or []
    }
    return sorted(names, key=str.casefold)


def get_patient_records(patient_id):
    result = collection.get(
        where={"patient_id": patient_id},
        include=["documents", "metadatas"],
    )
    grouped = {}
    for text, metadata in zip(result.get("documents") or [], result.get("metadatas") or []):
        name = metadata.get("document_id", "Unknown record")
        grouped.setdefault(name, []).append((metadata.get("chunk_index", 0), text))
    return [
        {"document_id": name, "text": "\n\n".join(text for _, text in sorted(chunks))}
        for name, chunks in sorted(grouped.items(), key=lambda item: item[0].casefold())
    ]


def delete_document(patient_id, document_id):
    result = collection.get(
        where={"patient_id": patient_id},
        include=["metadatas"],
    )
    ids = [
        record_id
        for record_id, metadata in zip(result.get("ids") or [], result.get("metadatas") or [])
        if metadata.get("document_id") == document_id
    ]
    if ids:
        collection.delete(ids=ids)


def get_patient_timeline(patient_id):
    result = collection.get(where={"patient_id": patient_id}, include=["documents", "metadatas"])
    events = {}
    patterns = [
        (r"heart attack.*?in\s+(\d{4})", "Previous heart attack", "Heart attack documented in the medical history."),
        (r"Consultation date\s*:?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", "Medical consultation", "Follow-up consultation documented in the medical record."),
        (r"(?:Date of (?:visit|service)|Visit date)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", "Medical visit", "Medical visit documented in the record."),
        (r"(?:\bDiagnosis\s*:\s*|\bDiagnosed with\s+)([^\n.;]+)", "Diagnosis", "Diagnosis listed in the medical record."),
    ]
    for doc, meta in zip(result.get("documents") or [], result.get("metadatas") or []):
        for pattern, title, description in patterns:
            for match in re.finditer(pattern, doc, re.I):
                value = match.group(1).strip()
                year_match = re.search(r"\d{4}", value)
                event_date = year_match.group() if year_match else value
                event_title = f"Diagnosis: {value}" if title == "Diagnosis" else title
                if title == "Diagnosis" and not year_match:
                    event_date = "Date not recorded"
                source = meta.get("document_id", "record")
                event = (event_date, event_title, description, source)
                events[(event_date, event_title, value, source)] = event
    def sort_key(event):
        match = re.search(r"\d{4}", event[0])
        return (int(match.group()) if match else 0, event[1])
    return sorted(events.values(), key=sort_key)


def _access_connection():
    db = sqlite3.connect(ACCESS_DB)
    db.execute("CREATE TABLE IF NOT EXISTS access_codes (patient_id TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at REAL NOT NULL)")
    return db


def create_access_code(patient_id, lifetime_seconds=600):
    code = secrets.token_urlsafe(16)
    digest = hashlib.sha256(code.encode()).hexdigest()
    with _access_connection() as db:
        db.execute("INSERT OR REPLACE INTO access_codes VALUES (?, ?, ?)", (patient_id, digest, time.time() + lifetime_seconds))
    return code


def verify_access_code(patient_id, code):
    if not code:
        return False
    with _access_connection() as db:
        row = db.execute("SELECT code_hash, expires_at FROM access_codes WHERE patient_id = ?", (patient_id,)).fetchone()
    return bool(row and time.time() < row[1] and secrets.compare_digest(row[0], hashlib.sha256(code.encode()).hexdigest()))


def revoke_access_code(patient_id):
    with _access_connection() as db:
        db.execute("DELETE FROM access_codes WHERE patient_id = ?", (patient_id,))




ACCOUNT_DB = BASE_DIR / "patient_accounts.sqlite3"
PASSWORD_ITERATIONS = 310_000
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _patient_account_connection():
    db = sqlite3.connect(str(ACCOUNT_DB))
    db.execute(
        """CREATE TABLE IF NOT EXISTS patient_accounts (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            patient_id TEXT NOT NULL UNIQUE,
            password_salt BLOB NOT NULL,
            password_hash BLOB NOT NULL,
            created_at REAL NOT NULL
        )"""
    )
    return db


def register_patient(email, password):
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    if len(password) < 8:
        raise ValueError("Choose a password with at least 8 characters.")
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    patient_id = "PAT-" + secrets.token_hex(8).upper()
    try:
        with _patient_account_connection() as db:
            db.execute(
                "INSERT INTO patient_accounts (email, patient_id, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (email, patient_id, salt, password_hash, time.time()),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with this email already exists. Sign in instead.") from exc
    return {"email": email, "patient_id": patient_id}


def authenticate_patient(email, password):
    email = email.strip().lower()
    with _patient_account_connection() as db:
        row = db.execute(
            "SELECT email, patient_id, password_salt, password_hash FROM patient_accounts WHERE email = ?",
            (email,),
        ).fetchone()
    if not row:
        return None
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), row[2], PASSWORD_ITERATIONS)
    if not secrets.compare_digest(candidate, row[3]):
        return None
    return {"email": row[0], "patient_id": row[1]}
