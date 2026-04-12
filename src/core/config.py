import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# API Configuration
_port_env = os.getenv("PORT", "8000")
PORT = int(_port_env) if str(_port_env).strip().isdigit() else 8000
HOST = os.getenv("HOST", "0.0.0.0")

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
_ttl_env = os.getenv("SESSION_TTL_SECONDS", "604800")
SESSION_TTL_SECONDS = int(_ttl_env) if str(_ttl_env).strip().isdigit() else 604800


def check_keys():
    if not GROQ_API_KEY:
        print("Warning: Missing GROQ_API_KEY in .env file.")
    if not GEMINI_API_KEY:
        print("Warning: Missing GEMINI_API_KEY in .env file.")
