import json
import logging
import os

from config import (
    TEACHER_MODEL, AUDITOR_MODEL, OUTPUT_DIR,
    KB_RAG_PLACEHOLDER, MAX_RETRIEVAL_REQUESTS,
    STM_PATH, USER_LEVEL,
    get_registry_path, get_concept_path,
)
from llm_client import call_llm, call_llm_messages
from prompts import load_prompt
from disk_utils import parse_block, apply_delta, read_file, write_file
from skeleton_builder import get_all_subsections, fmt_skeleton_condensed, fmt_skeleton_up_to_section
logger = logging.getLogger(__name__)

SUMMARIES_DIR = os.path.join(OUTPUT_DIR, "summaries")
CONTENT_DIR   = os.path.join(OUTPUT_DIR, "content")

BOOTSTRAP_STM = (
    "This is the first subsection of the textbook. No prior content exists."
)

MAX_RETRIES = 3


# ── Public entry point ────────────────────────────────────────────────────────

def run_phase3(skeleton: dict):
    subsections  = get_all_subsections(skeleton)
    skeleton_str = fmt_skeleton_condensed(skeleton)   # condensed, not json.dumps

    stm   = read_file(STM_PATH) or BOOTSTRAP_STM
    total = len(subsections)

    for i, sub in enumerate(subsections):
        sub_id   = sub["id"]
        sub_name = sub["name"]
        ch_id    = sub["chapter_id"]
        sec_id   = sub["section_id"]

        # Ensure per-section files exist before any reads/writes
        reg_path  = get_registry_path(ch_id, sec_id)
        conc_path = get_concept_path(ch_id, sec_id)
        _ensure_file(reg_path)
        _ensure_file(conc_path)

        # ── Resume check — both files must exist AND be non-empty ─────────────
        content_path = os.path.join(CONTENT_DIR,   f"{sub_id}.md")
        summary_path = os.path.join(SUMMARIES_DIR, f"{sub_id}.txt")

        if _file_ok(content_path) and _file_ok(summary_path):
            logger.info(f"[{i+1}/{total}] Subsection {sub_id}: already done, skipping")
            stm = read_file(STM_PATH) or stm
            continue

        # Content exists but summary missing/empty → Turn 3b crashed last time
        if _file_ok(content_path) and not _file_ok(summary_path):
            logger.info(
                f"[{i+1}/{total}] Subsection {sub_id}: content exists but summary "
                f"missing/empty — re-running Turn 3b onwards"
            )
            content        = read_file(content_path)
            next_name      = subsections[i + 1]["name"] if i + 1 < total else ""
            next_next_name = subsections[i + 2]["name"] if i + 2 < total else ""
            stm      = _turn3b_stm_summary(sub_id, sub_name, content, next_name, next_next_name)
            registry = read_file(reg_path)
            _turn3c_delta(sub_id, sub_name, content, registry, ch_id, sec_id)
            logger.info(f"Subsection {sub_id} complete.")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"[{i+1}/{total}] Subsection {sub_id}: {sub_name}")
        logger.info(f"{'='*60}")

        next_name      = subsections[i + 1]["name"] if i + 1 < total else ""
        next_next_name = subsections[i + 2]["name"] if i + 2 < total else ""

        # Current section's registry only — not global
        registry = read_file(reg_path)

        # Generate the truncated skeleton for Prompt 4
        skeleton_past_str = fmt_skeleton_up_to_section(skeleton, sec_id)

        fetched_summaries, fetched_concepts = _turn1_retrieval(
            sub_id, sub_name, skeleton_past_str, stm, skeleton, subsections, i,
        )
        outline = _turn2a_outline(
            sub_id, sub_name, skeleton_str, stm,
            registry, fetched_summaries, fetched_concepts,
        )
        annotated_outline = _turn3a_review(
            sub_id, sub_name, outline, registry,
        )
        content = _turn2b_content(
            sub_id, sub_name, skeleton_str, stm,
            registry, fetched_summaries, fetched_concepts, annotated_outline,
        )
        stm = _turn3b_stm_summary(
            sub_id, sub_name, content, next_name, next_next_name,
        )
        _turn3c_delta(sub_id, sub_name, content, registry, ch_id, sec_id)

        logger.info(f"Subsection {sub_id} complete.")


# ── File helpers ──────────────────────────────────────────────────────────────

def _file_ok(path: str) -> bool:
    """True only if the file exists and is non-empty."""
    return os.path.exists(path) and os.path.getsize(path) > 0


def _ensure_file(path: str):
    """Create an empty file if it does not exist yet."""
    if not os.path.exists(path):
        write_file(path, "")


# ── Retry wrapper (for auditor turns that must emit specific tags) ─────────────

def _call_auditor_with_retry(
    system: str,
    user: str,
    required_tags: list[str],
) -> dict[str, str]:
    """
    Call the auditor model, verify all required_tags are present and non-empty.
    On failure, send the model back its own response with specific feedback.
    Returns a dict of {tag: content}.
    Falls back to best-effort on exhaustion rather than crashing.
    """
    messages = [{"role": "user", "content": user}]

    for attempt in range(MAX_RETRIES + 1):
        response = call_llm_messages(AUDITOR_MODEL, system, messages)

        parsed  = {tag: parse_block(response, tag) for tag in required_tags}
        missing = [tag for tag, val in parsed.items() if not val.strip()]

        if not missing:
            if attempt > 0:
                logger.info(f"    Auditor retry {attempt} succeeded")
            return parsed

        error_desc = (
            f"The following required blocks were missing or empty in your response: "
            f"{', '.join(f'<{t}>' for t in missing)}.\n"
            f"You must emit ALL of: "
            f"{', '.join(f'<{t}>...</{t}>' for t in required_tags)}."
        )

        if attempt == MAX_RETRIES:
            logger.error(
                f"Auditor: all {MAX_RETRIES} retries exhausted. "
                f"Missing tags: {missing}. Using best-effort output."
            )
            return parsed   # caller handles empty strings gracefully

        logger.warning(f"  Auditor attempt {attempt + 1} failed: {error_desc} — retrying")
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user",      "content": (
            f"{error_desc}\n\n"
            f"Your previous response was:\n{response[:1000]}\n\n"
            f"Emit the corrected response now with all required blocks present."
        )})

    return {}   # unreachable but keeps type checker happy


# ── Turn implementations ──────────────────────────────────────────────────────

def _turn1_retrieval(
    sub_id, sub_name, skeleton_past_str, stm,
    skeleton, subsections, current_index,
) -> tuple[str, str]:
    """
    Ask the teacher what context it needs.
    Returns (fetched_summaries, fetched_concepts).
    """
    logger.info("  Turn 1 — teacher retrieval request")

    # Tell the model exactly which sections are available for concept retrieval
    completed_secs = _completed_sections(skeleton, subsections, current_index)
    available_concept_sections = _fmt_available_concept_sections(completed_secs, skeleton)

    system, user = load_prompt(4, {
        "subsection_id":              sub_id,
        "subsection_name":            sub_name,
        "skeleton_past":              skeleton_past_str, # <--- Updated variable name
        "stm":                        stm,
        "rag_chunks":                 KB_RAG_PLACEHOLDER,
        "user_level":                 USER_LEVEL,
        "available_concept_sections": available_concept_sections,
    })
    response = call_llm(TEACHER_MODEL, system, user)
    retrieval = _parse_retrieval_request(response, subsections, current_index,
                                        skeleton, completed_secs)

    fetched_summaries = _fetch_summaries(retrieval["summaries"])
    fetched_concepts  = _fetch_concepts(retrieval["concept_sections"], skeleton)

    logger.info(f"    Requested summaries:         {retrieval['summaries']}")
    logger.info(f"    Requested concept sections:  {retrieval['concept_sections']}")
    return fetched_summaries, fetched_concepts


def _turn2a_outline(
    sub_id, sub_name, skeleton_str, stm,
    registry, fetched_summaries, fetched_concepts,
) -> str:
    logger.info("  Turn 2a — teacher CoT outline")
    system, user = load_prompt(5, {
        "subsection_id":     sub_id,
        "subsection_name":   sub_name,
        "skeleton":          skeleton_str,
        "stm":               stm,
        "registry_txt":      registry,
        "fetched_summaries": fetched_summaries,
        "fetched_concepts":  fetched_concepts,
        "rag_chunks":        KB_RAG_PLACEHOLDER,
        "user_level":        USER_LEVEL,
    })
    response = call_llm(TEACHER_MODEL, system, user)
    return parse_block(response, "OUTLINE")


def _turn3a_review(sub_id, sub_name, outline, registry) -> str:
    logger.info("  Turn 3a — auditor outline review")
    system, user = load_prompt(6, {
        "subsection_id":   sub_id,
        "subsection_name": sub_name,
        "cot_outline":     outline,
        "registry_txt":    registry,
        "user_level":      USER_LEVEL,
    })
    response = call_llm(AUDITOR_MODEL, system, user)
    return parse_block(response, "ANNOTATED_OUTLINE")


def _turn2b_content(
    sub_id, sub_name, skeleton_str, stm,
    registry, fetched_summaries, fetched_concepts, annotated_outline,
) -> str:
    logger.info("  Turn 2b — teacher content generation")
    system, user = load_prompt(7, {
        "subsection_id":     sub_id,
        "subsection_name":   sub_name,
        "skeleton":          skeleton_str,
        "stm":               stm,
        "registry_txt":      registry,
        "fetched_summaries": fetched_summaries,
        "fetched_concepts":  fetched_concepts,
        "rag_chunks":        KB_RAG_PLACEHOLDER,
        "annotated_outline": annotated_outline,
        "user_level":        USER_LEVEL,
    })
    response = call_llm(TEACHER_MODEL, system, user)
    content  = parse_block(response, "CONTENT")

    write_file(os.path.join(CONTENT_DIR, f"{sub_id}.md"), content)
    logger.info(f"    Content written → {sub_id}.md")
    return content


def _turn3b_stm_summary(
    sub_id, sub_name, content, next_name, next_next_name,
) -> str:
    """Calls auditor with retry. Returns new STM and persists both STM and summary."""
    logger.info("  Turn 3b — auditor STM + summary file")
    system, user = load_prompt(8, {
        "subsection_id":              sub_id,
        "subsection_name":            sub_name,
        "subsection_content":         content,
        "next_subsection_name":       next_name,
        "subsection_after_next_name": next_next_name,
        "user_level":                 USER_LEVEL,
    })

    parsed  = _call_auditor_with_retry(system, user, required_tags=["STM", "SUMMARY"])
    new_stm = parsed.get("STM",     "").strip()
    summary = parsed.get("SUMMARY", "").strip()

    if not new_stm:
        logger.error(f"  Turn 3b: STM empty after retries for {sub_id} — keeping previous STM")
    if not summary:
        logger.error(f"  Turn 3b: SUMMARY empty after retries for {sub_id} — writing empty file")

    write_file(os.path.join(SUMMARIES_DIR, f"{sub_id}.txt"), summary)
    logger.info(f"    Summary written → {sub_id}.txt")

    if new_stm:
        write_file(STM_PATH, new_stm)

    return new_stm or read_file(STM_PATH)   # fall back to last good STM


def _turn3c_delta(sub_id, sub_name, content, registry, ch_id, sec_id):
    """
    Auditor emits notation and concept deltas.
    Registry delta → upserted into the current section's registry file.
    Concept delta  → upserted into the current section's concept file.
    Auditor receives the current section registry so it avoids within-section
    symbol duplication. It does NOT receive the concept file — emits freely.
    """
    logger.info("  Turn 3c — auditor registry + concept index delta")
    system, user = load_prompt(9, {
        "subsection_id":      sub_id,
        "subsection_name":    sub_name,
        "subsection_content": content,
        "registry_txt":       registry,
        "user_level":         USER_LEVEL,
    })
    response = call_llm(AUDITOR_MODEL, system, user)

    registry_delta = parse_block(response, "REGISTRY_DELTA")
    concept_delta  = parse_block(response, "CONCEPT_DELTA")

    if registry_delta:
        apply_delta(registry_delta, get_registry_path(ch_id, sec_id), "SYMBOL")
    else:
        logger.debug(f"  Turn 3c: no registry delta for {sub_id}")

    if concept_delta:
        apply_delta(concept_delta, get_concept_path(ch_id, sec_id), "CONCEPT")
    else:
        logger.debug(f"  Turn 3c: no concept delta for {sub_id}")


# ── Retrieval helpers ─────────────────────────────────────────────────────────

def _parse_retrieval_request(
    response: str, subsections: list, current_index: int,
    skeleton: dict, completed_secs: set,
) -> dict:
    """
    Parse the teacher's retrieval request.

    Expected format inside <RETRIEVAL_REQUEST>...</RETRIEVAL_REQUEST>:
        {
            "summaries":        [{"subsection_id": "1.1.3", "reason": "..."}, ...],
            "concept_sections": [{"section_id": "1.1", "reason": "..."}, ...]
        }

    Also handles plain-string lists in case the model simplifies:
        {"summaries": ["1.1.3", "1.2.1"], "concept_sections": ["1.1"]}

    Returns {"summaries": [...], "concept_sections": [...]}.
    """
    raw = parse_block(response, "RETRIEVAL_REQUEST")
    if not raw:
        return {"summaries": [], "concept_sections": []}

    try:
        parsed = json.loads(raw.strip())
    except json.JSONDecodeError:
        logger.warning("_parse_retrieval_request: could not parse JSON — returning empty")
        return {"summaries": [], "concept_sections": []}

    # ── Summary IDs — accept both {subsection_id, reason} dicts and plain strings ──
    raw_summary_ids = []
    for s in parsed.get("summaries", []):
        if isinstance(s, dict):
            sid = s.get("subsection_id") or s.get("id")
            if sid:
                raw_summary_ids.append(str(sid))
        elif isinstance(s, str) and s:
            raw_summary_ids.append(s)

    all_prior_ids = {s["id"] for s in subsections[:current_index]}
    prev_id       = subsections[current_index - 1]["id"] if current_index > 0 else None
    valid_sub_ids = all_prior_ids - ({prev_id} if prev_id else set())

    filtered_subs = [sid for sid in raw_summary_ids if sid in valid_sub_ids]
    for sid in set(raw_summary_ids) - set(filtered_subs):
        if sid == prev_id:
            logger.debug(
                f"Summary {sid} not fetched — already in STM (immediate predecessor)"
            )
        elif sid not in all_prior_ids:
            logger.warning(
                f"Summary {sid} dropped — does not exist in skeleton or not yet written"
            )
        else:
            logger.warning(f"Summary {sid} dropped — unknown reason")

    # ── Concept section IDs — accept both {section_id, reason} dicts and plain strings ──
    raw_section_ids = []
    for s in parsed.get("concept_sections", []):
        if isinstance(s, dict):
            sid = s.get("section_id") or s.get("id")
            if sid:
                raw_section_ids.append(str(sid))
        elif isinstance(s, str) and s:
            raw_section_ids.append(s)

    filtered_secs = [sid for sid in raw_section_ids if sid in completed_secs]
    for sid in set(raw_section_ids) - set(filtered_secs):
        logger.warning(
            f"Concept section {sid} dropped — section not yet fully complete"
        )

    return {
        "summaries":        filtered_subs[:MAX_RETRIEVAL_REQUESTS],
        "concept_sections": filtered_secs,
    }


def _completed_sections(skeleton: dict, subsections: list, current_index: int) -> set:
    """
    Return the set of section IDs where ALL subsections are before current_index
    (i.e. the section is fully written and its concept file is complete).
    """
    done_ids = {s["id"] for s in subsections[:current_index]}
    completed = set()
    for ch in skeleton["chapters"]:
        for sec in ch["sections"]:
            sec_sub_ids = {sub["id"] for sub in sec.get("subsections", [])}
            if sec_sub_ids and sec_sub_ids.issubset(done_ids):
                completed.add(str(sec["id"]))
    return completed


def _fmt_available_concept_sections(completed_secs: set, skeleton: dict) -> str:
    """
    Human-readable list of section IDs whose concept files are fully available,
    passed to Prompt 4 so the model knows exactly what it can request.
    """
    if not completed_secs:
        return "None — no sections are fully complete yet."
    lines = []
    for ch in skeleton["chapters"]:
        for sec in ch["sections"]:
            if str(sec["id"]) in completed_secs:
                lines.append(f"  {sec['id']} — {sec['name']}")
    return "\n".join(lines) if lines else "None available."


def _fetch_summaries(requested_ids: list[str]) -> str:
    if not requested_ids:
        return "No prior subsection summaries requested."

    parts = []
    for sid in requested_ids:
        path = os.path.join(SUMMARIES_DIR, f"{sid}.txt")

        if not os.path.exists(path):
            logger.warning(f"Summary not found (subsection not yet processed?): {sid}")
            parts.append(f"--- Summary {sid} --- [not yet generated]")
        elif os.path.getsize(path) == 0:
            logger.warning(f"Summary file exists but is empty: {sid}")
            parts.append(f"--- Summary {sid} --- [file is empty — generation may have failed]")
        else:
            parts.append(f"--- Summary {sid} ---\n{read_file(path)}")

    return "\n\n".join(parts)


def _fetch_concepts(section_ids: list[str], skeleton: dict) -> str:
    """
    Fetch and concatenate the concept files for the requested section IDs.
    Concept files are per-section: concepts_ch{ch_id}_sec{sec_id_safe}.txt
    """
    if not section_ids:
        return "No concept sections requested."

    parts = []
    for sec_id in section_ids:
        ch_id = _find_chapter_for_section(sec_id, skeleton)
        if ch_id is None:
            logger.warning(f"_fetch_concepts: could not find chapter for section {sec_id}")
            continue

        path = get_concept_path(ch_id, sec_id)

        if not os.path.exists(path):
            logger.warning(f"Concept file not found for section {sec_id}")
            parts.append(f"--- Concepts section {sec_id} --- [not yet generated]")
        elif os.path.getsize(path) == 0:
            logger.warning(f"Concept file is empty for section {sec_id}")
            parts.append(f"--- Concepts section {sec_id} --- [empty]")
        else:
            parts.append(f"--- Concepts section {sec_id} ---\n{read_file(path)}")

    return "\n\n".join(parts) if parts else "No concept sections found."


def _find_chapter_for_section(sec_id: str, skeleton: dict) -> int | None:
    """Walk the skeleton to find which chapter owns this section ID."""
    for ch in skeleton["chapters"]:
        for sec in ch["sections"]:
            if str(sec["id"]) == sec_id:
                return ch["id"]
    return None