# MeetingMind AI - SaaS Meeting Analyzer

MeetingMind AI is a production-ready SaaS web application designed to automatically upload meeting recordings, convert speech to text, generate AI-powered summaries, extract action items/decisions, detect sentiment trends, provide downloadable PDF reports, and offer a semantic RAG chatbot to query meeting transcripts.

---

## Features

- **Authentication**: JWT token authentication (Signup, Login, Get Profile).
- **Dashboard**: Global metrics cards (Meetings, Action Items, Tasks), recent uploads log, dynamic Recharts visualizations.
- **File Upload**: Supports MP3, WAV, M4A up to 50MB with drag-and-drop validation and processing tracker.
- **AI Whisper Speech-to-Text**: Transcription engine with an automatic local mock transcription fallback.
- **Meeting Summarization**: Generates Executive summaries, Detailed summaries, and Bullet highlights.
- **Action Items Table**: Formats extracted action items with Task, Owner, Deadline, Priority in an inline-editable grid.
- **Key Decisions & Risks**: Extracts critical agreements, follow-ups, and project risks.
- **Sentiment Analysis**: Tracks Positive/Neutral/Negative scores and charts them.
- **Interactive Chatbot**: RAG search over transcripts using cosine similarity queries (ChromaDB or custom Python SQLite vector engine).
- **PDF Report Exporter**: Professional PDF compilations featuring headers, grid tables, and summaries.
- **Admin Panel**: Manage registered user pools, purge meetings, review API workloads, and audit platform activity.

---

## Tech Stack

- **Frontend**: React (Vite), Tailwind CSS, React Router v6, Axios, Recharts, Lucide Icons.
- **Backend**: FastAPI (Python), Uvicorn, SQLAlchemy.
- **Database**: SQLite (Development) / PostgreSQL compatible (Production).
- **AI/ML Layer**: OpenAI Whisper, Google Gemini API, ChromaDB (with local mock/NLP heuristics fallback).
- **PDF Exporting**: ReportLab PDF library.

---

## Folder Structure

```
MeetingMindAI/
├── backend/              # FastAPI Application (Python)
│   ├── app/
│   │   ├── main.py       # API configuration & routes linking
│   │   ├── config.py     # Env loaders & Folder creators
│   │   ├── database.py   # SQLAlchemy setup & session yielders
│   │   ├── models.py     # Users, Meetings, ActionItems, Decisions models
│   │   ├── schemas.py    # Request & response validations (Pydantic)
│   │   ├── routers/      # API endpoints split (auth, meetings, admin)
│   │   ├── services/     # Core Whisper, Gemini, PDF, Vector RAG managers
│   │   └── utils.py      # JWT, Bcrypt password hashing
│   ├── requirements.txt  # Python requirements
│   └── Dockerfile        # Backend docker container
├── frontend/             # Vite React client
│   ├── src/
│   │   ├── context/      # Auth state contexts
│   │   ├── components/   # Sidebar layouts
│   │   ├── pages/        # Login, Signup, Dashboard, Details, Admin
│   │   ├── utils/        # Axios API clients
│   │   ├── index.css     # Tailwind styling & animations
│   │   └── main.jsx      # React DOM client mounting
│   ├── tailwind.config.js
│   ├── index.html        # HTML page with Inter google font
│   └── Dockerfile        # Frontend production builder container
├── database/             # SQLite folder
├── uploads/              # Preserved audio recordings
├── reports/              # Preserved PDF reports
├── chromadb/             # Vector storage
└── docker-compose.yml    # Orchestrated compose manifest
```

---

## API Catalog Reference

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| **POST** | `/auth/signup` | Register a new user | No |
| **POST** | `/auth/login` | Login and acquire JWT access token | No |
| **GET** | `/auth/me` | Retrieve profile of active user | Yes |
| **POST** | `/upload` | Upload audio recording (MP3, WAV, M4A) | Yes |
| **POST** | `/transcribe` | Dispatch file to Whisper transcription | Yes |
| **POST** | `/summarize` | Generate summaries and sentiment scores | Yes |
| **POST** | `/extract-actions` | Save action items and decision points | Yes |
| **POST** | `/generate-report` | Compile and retrieve PDF report file | Yes |
| **POST** | `/chat` | Chat with meeting content using RAG query | Yes |
| **GET** | `/meetings` | List current user's meetings | Yes |
| **GET** | `/meeting/{id}` | Retrieve single meeting analysis workspace | Yes |
| **DELETE** | `/meeting/{id}` | Purge meeting audio, DB items, and index | Yes |
| **GET** | `/admin/analytics`| Fetch global platform statistics | Yes (Admin) |
| **GET** | `/admin/users` | List platform users and statistics | Yes (Admin) |
| **DELETE** | `/admin/users/{id}`| Purge user, meetings, and vectors | Yes (Admin) |

---

## Setup & Running Guide

### Method A: Docker Compose (Recommended)

1. Create a `.env` file in the root directory from the template:
   ```bash
   cp .env.example .env
   ```
2. Insert your OpenAI and Gemini API keys into `.env` (optional, the code will fall back to local mock NLP processing if empty).
3. Build and launch all containers:
   ```bash
   docker-compose up --build
   ```
4. Access the React app at `http://localhost:3000` and the API documentation at `http://localhost:8000/docs`.

---

### Method B: Manual Local Development

#### 1. Setup Backend
1. Move to backend folder:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

#### 2. Setup Frontend
1. Open a new terminal and navigate to the frontend folder:
   ```bash
   cd frontend
   ```
2. Install Node dependencies:
   ```bash
   npm install
   ```
3. Launch the Vite development server:
   ```bash
   npm run dev
   ```
4. Access the workspace client in your browser at `http://localhost:5173`.

---

## Verification & Fallback Behavior

- **Initial Account**: The first user registered on the system will automatically be designated the `admin` role, gaining access to the Admin Control Panel in the navigation sidebar. Subsequent signups are labeled `user`.
- **API Fallbacks**: If `OPENAI_API_KEY` or `GEMINI_API_KEY` are not configured in `.env`, the system automatically runs built-in mock services. This allows full evaluation of transcription logs, summary tab views, Recharts statistics, PDF reports, and chatbot inputs out-of-the-box.
