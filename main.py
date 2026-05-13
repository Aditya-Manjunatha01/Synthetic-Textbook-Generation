"""
Synthetic Textbook Generation Pipeline

Configuration:
    Edit TOPIC and USER_LEVEL in config.py before running.

Usage:
    python main.py

Resume:
    Just run the same command again — the pipeline resumes automatically
    from the last completed checkpoint.
"""

import logging
import os

from config import OUTPUT_DIR, SKELETON_PATH, STM_PATH, TOPIC
from disk_utils import write_file
from skeleton_builder import build_skeleton
from phase3_loop import run_phase3


def setup_logging():
    log_dir = os.path.join(OUTPUT_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(log_dir, "pipeline.log")),
        ],
    )


def init_output_dir():
    """Create all required output subdirectories."""
    for subdir in ["summaries", "content", "logs", "registry", "concepts"]:
        os.makedirs(os.path.join(OUTPUT_DIR, subdir), exist_ok=True)
    # registry and concept files are per-section, created on demand by
    # _ensure_file() in phase3_loop — no pre-initialisation needed here.


def main():
    setup_logging()
    init_output_dir()

    logger = logging.getLogger(__name__)
    logger.info(f"Pipeline starting — topic: {TOPIC}")

    skeleton = build_skeleton(TOPIC)
    run_phase3(skeleton)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()