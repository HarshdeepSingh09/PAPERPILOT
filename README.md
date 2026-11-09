# PAPERPILOT
An AI-powered document intelligence platform that lets users interact with PDFs, generate summaries, create quizzes, and retrieve contextual answers using RAG.

---

## 🛠️ Architecture & Tech Stack

* **Frontend:** React 18, Vite, TypeScript, Tailwind CSS, Lucide Icons, Axios
* **Backend:** Python 3.14, FastAPI, Uvicorn, SQLAlchemy (SQLite ORM), PyMuPDF (`fitz`)
* **Vector Store & Embeddings:** ChromaDB & Google Generative AI (Gemini embeddings)
* **RAG Orchestration:** LangChain
* **LLM Engine:** Google Gemini API (Gemini 1.5 Flash)

---

## 📁 Repository Structure

```
PAPERPILOT/
│
├── .gitignore                    # Excludes venv, node_modules, .env, *.db, and uploads
├── README.md                     # Project documentation & run guide
│
├── backend/                      # Python + FastAPI backend service
│   ├── .env.example              # Template for server & AI keys (copy to .env)
│   ├── requirements.txt          # Python dependencies
│   ├── storage/                  # Local persistence (ignored by Git)
│   │   ├── uploads/              # Raw uploaded PDF documents
│   │   └── chroma_db/            # ChromaDB vector index collections
│   └── app/
│       ├── main.py               # FastAPI application entry & CORS middleware
│       ├── core/                 # App configurations & settings
│       ├── db/                   # SQLite session and SQLAlchemy models
│       ├── schemas/              # Pydantic request/response schemas
│       ├── services/             # PDF parsing, ChromaDB, and RAG/AI service interfaces
│       └── api/                  # REST API routes (/api/v1/documents, /chat, etc.)
│
└── frontend/                     # React + Vite + Tailwind CSS SPA
    ├── .env.example              # Frontend environment variables template
    ├── package.json              # NPM dependencies & scripts
    ├── vite.config.ts            # Vite config with backend API reverse proxy
    ├── tailwind.config.js        # Tailwind CSS configuration
    └── src/
        ├── App.tsx               # Workspace layout & view controller
        ├── api/                  # Axios HTTP client connecting to FastAPI
        ├── components/           # UI components (Chat, PDF viewer, Summaries, Quizzes)
        └── types/                # TypeScript interfaces
```

---

## 🚀 Running the Project

### 1. Backend (FastAPI)

1. Open a terminal in `backend/`:
   ```bash
   cd backend
   ```
2. Activate the Python virtual environment:
   * **Windows (PowerShell):**
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   * **Windows (Command Prompt):**
     ```cmd
     .\venv\Scripts\activate.bat
     ```
   * **Linux/macOS:**
     ```bash
     source venv/bin/activate
     ```
3. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
4. Start the development server:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   * The API will be available at `http://127.0.0.1:8000`
   * Interactive Swagger documentation is at `http://127.0.0.1:8000/api/v1/docs`

---

### 2. Frontend (React + Vite)

1. Open a separate terminal in `frontend/`:
   ```bash
   cd frontend
   ```
2. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
4. Open your browser and navigate to `http://localhost:5173`.
