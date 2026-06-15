"""Environment-driven configuration. Demo defaults are 100% free; production swaps via env vars."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent          # demo/backend
DEMO_DIR = BASE_DIR.parent                           # demo
DATA_DIR = DEMO_DIR / "data"
SEED_DIR = DATA_DIR / "seed"
SAMPLES_DIR = DATA_DIR / "samples"
FRONTEND_DIR = DEMO_DIR / "frontend"

DATA_DIR.mkdir(parents=True, exist_ok=True)

MODE = os.getenv("DRISHTI_MODE", "demo")
DEFAULT_DB = f"sqlite:///{(DATA_DIR / 'drishti_demo.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB)

# Assistant: 'none' => free extractive grounded answers; otherwise call a provider with a key.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

APP_TITLE = "DRISHTI — Crime Intelligence & Analytical Platform"
APP_VERSION = "1.0-demo"
