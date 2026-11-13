# One Patient, Many Records

A Streamlit prototype that brings a patient's text-based PDF records together in one workspace. It can search the saved text, build a simple medical timeline, and create a time-limited QR link for a doctor to view shared records.

## Features

- Patient accounts with email and password. Passwords are stored as salted PBKDF2 hashes.
- Upload and extract text from selectable-text PDF files.
- Store record text locally in a ChromaDB collection and search it by patient ID.
- Build a basic timeline from dates, diagnoses, and selected medical-history phrases found in records.
- Create a read-only doctor page through a private QR link. Access expires after 10 minutes and can be revoked sooner.
- Optional microphone input for the search box. The browser may process speech recognition; the resulting text is then searched locally.

## Requirements

- Python 3.10 or newer
- A modern browser for the Streamlit interface
- Chrome or Edge is recommended for microphone search. Microphone access requires browser permission and a secure context (HTTPS or localhost).

## Run locally

From the project folder, create and activate a virtual environment, install the dependencies, and start Streamlit:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local address printed in the terminal. Create a patient account the first time, then sign in with that account on later visits.

## Share records with a doctor

1. Open **Doctor access** in the patient workspace.
2. Set **App address for the doctor device** to an address the doctor's phone can reach. On the same Wi-Fi, use the computer's local network address. For remote access, use the deployed app's HTTPS address.
3. Authorize temporary sharing and choose **Generate access code**.
4. Let the doctor scan the displayed QR code. The link opens a separate read-only doctor page and expires after 10 minutes. Choose **Revoke current access** to end it sooner.

Keep the QR link private. Anyone who has the active link can open the shared records until it expires or is revoked.

## How search works

PDF text is split into chunks and stored in ChromaDB with locally generated hashed word and word-pair vectors. Search retrieves matching chunks, then the app uses simple extraction rules or returns a relevant excerpt. This is a lightweight RAG-style retrieval flow; it does not use Ollama, a generative language model, or a hosted AI service.

Microphone dictation is separate from record search. Speech recognition may be handled by the browser provider, so use typed search if you do not want to use browser-based speech processing.

## Local data and prototype limits

The app stores extracted record text in the local `chroma_db/` folder. Patient accounts and temporary access codes are kept in local SQLite files. Those files, `.env`, and PDF files are excluded from Git by `.gitignore`.

This is a prototype, not a production medical-record system. Before using real patient information in a deployment, add appropriate hosting security, backups, account recovery, audit logging, and privacy/legal review. Do not expose the Streamlit development server directly to the public internet.
