import os
import sys
import logging
from pydantic_settings import BaseSettings
from pathlib import Path

logger = logging.getLogger(__name__)

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

_INSECURE_DEFAULT_KEY = "supersecretjwtkeyformeetingmindai"

class Settings(BaseSettings):
    # Security
    SECRET_KEY: str = _INSECURE_DEFAULT_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # CORS — comma-separated list of allowed origins (e.g. *,http://localhost:5173,https://app.example.com)
    CORS_ORIGINS: str = "*,http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000,http://127.0.0.1:3000,https://meeting-mind-aii.vercel.app"

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/database/meetingmind.db"

    # Directories
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    REPORT_DIR: str = str(BASE_DIR / "reports")
    CHROMA_DIR: str = str(BASE_DIR / "chromadb")

    # Asynchronous processing — number of transcription/analysis jobs that may
    # run concurrently in the in-process background worker pool. Keep this low:
    # transcription is CPU/GPU-heavy and shares a single in-process model.
    MAX_CONCURRENT_JOBS: int = 2

    # Transcription — preferred faster-whisper model; falls back to "small" then "tiny".
    # "large-v3-turbo" is multilingual (Hindi, English, 90+ languages) and fits a 4GB GPU.
    # Set to "distil-large-v3" for maximum English-only speed.
    WHISPER_MODEL: str = "large-v3-turbo"

    # Remote vLLM speech-LLM server (OpenAI-compatible), e.g. Ultravox on a GPU box.
    # Leave VLLM_BASE_URL empty to skip this engine entirely.
    # Example: http://your-gpu-server:8001/v1
    VLLM_BASE_URL: str = ""
    VLLM_MODEL: str = "ultravox"
    VLLM_API_KEY: str = "EMPTY"

    # Speaker diarization — label transcript turns as "Speaker 1: ...", etc.
    # When ENABLE_DIARIZATION is true, acoustic diarization runs only if
    # pyannote.audio is installed AND HUGGINGFACE_TOKEN grants access to the
    # gated diarization model; otherwise it gracefully falls back to a
    # text-based heuristic. Off by default so existing behaviour is unchanged.
    ENABLE_DIARIZATION: bool = False
    HUGGINGFACE_TOKEN: str = ""
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"

    # API Keys
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_MODEL: str = "openai:gpt-4o-mini"
    LANGGRAPH_API_KEY: str = ""
    LANGGRAPH_MODEL: str = "openai:gpt-4o-mini"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

# Create directories if they do not exist
settings = Settings()

if settings.SECRET_KEY == _INSECURE_DEFAULT_KEY:
    logger.warning(
        "SECURITY WARNING: SECRET_KEY is using the insecure default value. "
        "Set a strong SECRET_KEY in your .env file before deploying to production."
    )
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.REPORT_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(settings.DATABASE_URL.replace("sqlite:///", "")), exist_ok=True)
