import os

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST = "34.93.210.88"
API_PORT = 8080
API_KEY  = "Bearer gw-idMKBlwAA6aR0dV5u-HP5M76--41UqAvZmA31EWPI8E"

# ── Topic & Audience ──────────────────────────────────────────────────────────
TOPIC      = "thermodynamics"
USER_LEVEL = "undergraduate (third year)"

# ── Models ────────────────────────────────────────────────────────────────────
TEACHER_MODEL = "google/gemma-4-31B-it"
AUDITOR_MODEL = "google/gemma-4-31B-it"

# ── Paths (override via env vars if needed) ───────────────────────────────────
PROMPTS_DIR = os.environ.get("PROMPTS_DIR", "/home/airexlabadmin/aditya/pipeline/pipeline_prompts")
OUTPUT_DIR  = os.environ.get("OUTPUT_DIR",  "/home/airexlabadmin/aditya/pipeline/outputs_practical")

# ── Generation defaults ───────────────────────────────────────────────────────
MAX_TOKENS          = 50000   # Phase 3 content calls
SKELETON_MAX_TOKENS = 50000  # Skeleton calls — large JSON outputs need more room
TEMPERATURE         = 0.7

# ── Pipeline constants ────────────────────────────────────────────────────────
MAX_RETRIEVAL_REQUESTS = 999
KB_RAG_PLACEHOLDER     = "[No knowledge base chunks available for this run.]"

# ── Resume state files ────────────────────────────────────────────────────────
SKELETON_PATH = os.path.join(OUTPUT_DIR, "skeleton.json")
STM_PATH      = os.path.join(OUTPUT_DIR, "stm.txt")

# ── Per-section file path helpers ─────────────────────────────────────────────
# sec_id (e.g. "1.2") already encodes the chapter — ch_id is accepted for call
# compatibility but not used in the path.

def get_registry_path(ch_id: int, sec_id: str) -> str:
    """registry/registry_sec_1_2.txt  ←  section 1.2"""
    sec_safe = str(sec_id).replace(".", "_")
    return os.path.join(OUTPUT_DIR, "registry", f"registry_sec_{sec_safe}.txt")

def get_concept_path(ch_id: int, sec_id: str) -> str:
    """concepts/concepts_sec_1_2.txt  ←  section 1.2"""
    sec_safe = str(sec_id).replace(".", "_")
    return os.path.join(OUTPUT_DIR, "concepts", f"concepts_sec_{sec_safe}.txt")
