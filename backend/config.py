"""Configuration. Override values in backend/.env"""
import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
if load_dotenv:
    load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")   # use 0.0.0.0 to let students connect over the LAN
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = _bool("FLASK_DEBUG", False)

# Teacher controls
ALLOW_WRITE_PLAYGROUND = _bool("ALLOW_WRITE_PLAYGROUND", False)   # allow CREATE/MERGE/DELETE in the playground
ALLOW_RESET = _bool("ALLOW_RESET", True)                          # allow "Delete all data" in the UI

FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
NEO4J_SCRIPTS_DIR = os.path.join(PROJECT_DIR, "neo4j")
