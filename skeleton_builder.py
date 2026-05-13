import json
import logging
import os

from config import TEACHER_MODEL, OUTPUT_DIR, SKELETON_MAX_TOKENS, SKELETON_PATH, USER_LEVEL
from llm_client import call_llm, call_llm_messages
from prompts import load_prompt
from disk_utils import parse_json_response, write_file

logger = logging.getLogger(__name__)

_SECTIONS_DONE    = "_sections_done"
_SUBSECTIONS_DONE = "_subsections_done"

_GARBAGE_NAMES = {
    "", "name", "subsection", "subsections", "id", "type", "difficulty",
    "section", "chapter", "title", "...", "subsection name", "section name",
    "chapter name", "placeholder", "example", "description",
}

MAX_RETRIES               = 3
LOOKBACK_CHAPTERS         = 2
MIN_SUBSECTIONS_PER_SEC   = 5
MAX_SUBSECTIONS_PER_SEC   = 10


# ── Public entry point ────────────────────────────────────────────────────────

def build_skeleton(topic_name: str) -> dict:
    if os.path.exists(SKELETON_PATH):
        logger.info("Found existing skeleton.json — resuming")
        with open(SKELETON_PATH) as f:
            skeleton = json.load(f)
    else:
        skeleton = {
            "topic":            topic_name,
            _SECTIONS_DONE:    [],
            _SUBSECTIONS_DONE: [],
            "chapters":         [],
        }

    sections_done    = set(skeleton.get(_SECTIONS_DONE,    []))
    subsections_done = set(skeleton.get(_SUBSECTIONS_DONE, []))

    # ── Phase 1: chapter names ────────────────────────────────────────────────
    if not skeleton["chapters"]:
        logger.info("Phase 1: generating chapter outline …")
        system, user = load_prompt(1, {
            "topic_name": topic_name,
            "user_level": USER_LEVEL,
        })
        chapters_json = _call_with_retry(
            system, user,
            validate_fn=_validate_chapters,
        )
        for ch_id, ch_name in sorted(chapters_json.items(), key=lambda x: int(x[0])):
            skeleton["chapters"].append({
                "id": int(ch_id), "name": ch_name, "sections": [],
            })
        _save(skeleton)
        logger.info(f"  {len(skeleton['chapters'])} chapters")
    else:
        logger.info(f"Phase 1: skipping — {len(skeleton['chapters'])} chapters in skeleton")

    # ── Phase 1.1: section names ──────────────────────────────────────────────
    logger.info("Phase 1.1: generating section names …")
    for ch in skeleton["chapters"]:
        ch_id = ch["id"]
        if ch_id in sections_done:
            logger.info(f"  Chapter {ch_id}: already done, skipping")
            continue

        system, user = load_prompt(2, {
            "topic_name":                 topic_name,
            "chapter_list":               _fmt_chapter_list(skeleton["chapters"]),
            "chapter_id":                 ch_id,
            "chapter_name":               ch["name"],
            "previous_chapters_sections": _fmt_prev_sections(skeleton, sections_done),
            "user_level":                 USER_LEVEL,
        })
        secs_json = _call_with_retry(
            system, user,
            validate_fn=lambda p, cid=ch_id: _validate_sections(p, cid),
        )
        ch["sections"] = [
            {"id": sec_id, "name": sec_name, "subsections": []}
            for sec_id, sec_name in sorted(
                secs_json.items(),
                key=lambda x: [int(n) for n in x[0].split(".")],
            )
        ]
        sections_done.add(ch_id)
        skeleton[_SECTIONS_DONE] = list(sections_done)
        _save(skeleton)
        logger.info(f"  Chapter {ch_id}: {len(ch['sections'])} sections")

    # ── Phase 2: subsection names, one section at a time ─────────────────────
    logger.info("Phase 2: generating subsection names …")
    for ch_idx, ch in enumerate(skeleton["chapters"]):
        ch_id = ch["id"]

        if ch_id in subsections_done:
            logger.info(f"  Chapter {ch_id}: already done, skipping")
            continue

        # On resume: rebuild accumulator from sections already done in this chapter
        subsections_so_far = {}
        for sec in ch["sections"]:
            if sec["subsections"]:
                subsections_so_far[str(sec["id"])] = sec["subsections"]

        if subsections_so_far:
            logger.info(f"  Chapter {ch_id}: resuming from section "
                        f"{len(subsections_so_far) + 1}/{len(ch['sections'])}")

        # Inner loop: one call per section
        for sec in ch["sections"]:
            sec_id   = str(sec["id"])
            sec_name = sec["name"]

            if sec["subsections"]:
                logger.info(f"    Section {sec_id}: already done, skipping")
                continue

            system, user = load_prompt(3, {
                "topic_name":                         topic_name,
                "chapter_list":                       _fmt_chapter_list(skeleton["chapters"]),
                "previous_chapter_sections":          _fmt_previous_chapter_sections(skeleton, ch_idx),
                "chapter_id":                         ch_id,
                "chapter_name":                       ch["name"],
                "section_list":                       _fmt_section_list(ch["sections"]),
                "current_chapter_subsections_so_far": _fmt_subsections_so_far(subsections_so_far),
                "section_id":                         sec_id,
                "section_name":                       sec_name,
                "user_level":                         USER_LEVEL,
            })

            result = _call_with_retry(
                system, user,
                validate_fn=lambda p, sid=sec_id: _validate_section_subsections(p, sid),
            )

            # Parse — key is the section_id
            raw_subs           = result.get(sec_id, [])
            sec["subsections"] = _parse_subsection_list(raw_subs, sec_id)

            # Update accumulator for next section in this chapter
            subsections_so_far[sec_id] = sec["subsections"]

            # Checkpoint after every section
            _save(skeleton)
            logger.info(f"    Section {sec_id}: {len(sec['subsections'])} subsections")

        # Mark chapter fully done only after all sections complete
        subsections_done.add(ch_id)
        skeleton[_SUBSECTIONS_DONE] = list(subsections_done)
        _save(skeleton)
        total = sum(len(s["subsections"]) for s in ch["sections"])
        logger.info(f"  Chapter {ch_id}: {total} subsections total")

    logger.info(f"Skeleton complete → {SKELETON_PATH}")
    return skeleton


# ── Retry + feedback loop ─────────────────────────────────────────────────────

def _call_with_retry(system: str, user: str, validate_fn, max_retries: int = MAX_RETRIES) -> dict:
    messages = [{"role": "user", "content": user}]

    for attempt in range(max_retries + 1):
        response = call_llm_messages(
            TEACHER_MODEL, system, messages, max_tokens=SKELETON_MAX_TOKENS
        )

        try:
            parsed = parse_json_response(response)
            result = validate_fn(parsed)
            if attempt > 0:
                logger.info(f"    Retry {attempt} succeeded")
            return result

        except (ValueError, KeyError, TypeError) as e:
            error_desc = str(e)

            if attempt == max_retries:
                logger.error(
                    f"All {max_retries} retries exhausted. Last error: {error_desc}\n"
                    f"Falling back to best-effort parse."
                )
                try:
                    return parse_json_response(response)
                except Exception:
                    logger.error("Best-effort parse also failed — returning empty dict")
                    return {}

            logger.warning(
                f"  Attempt {attempt + 1} failed: {error_desc} — retrying with feedback"
            )
            feedback = (
                f"Your previous response had the following problem:\n\n"
                f"{error_desc}\n\n"
                f"Your response was:\n{response[:1000]}\n\n"
                f"Return only the corrected JSON. No preamble, no commentary, "
                f"no markdown fences."
            )
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user",      "content": feedback})


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_chapters(parsed: dict) -> dict:
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(f"Expected a non-empty JSON object, got: {type(parsed).__name__}")
    errors = []
    for k, v in parsed.items():
        try:
            int(k)
        except ValueError:
            errors.append(f"Key '{k}' is not an integer chapter ID")
        if not isinstance(v, str) or not v.strip():
            errors.append(f"Chapter {k}: name is empty or not a string")
        elif v.strip().lower() in _GARBAGE_NAMES:
            errors.append(f"Chapter {k}: name looks like a placeholder: {v!r}")
    if errors:
        raise ValueError("Chapter validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    return parsed


def _validate_sections(parsed: dict, chapter_id: int) -> dict:
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(f"Expected a non-empty JSON object, got: {type(parsed).__name__}")
    prefix = f"{chapter_id}."
    errors = []
    for k, v in parsed.items():
        if not k.startswith(prefix):
            errors.append(f"Key '{k}' does not start with chapter prefix '{prefix}'")
        if len(k.split(".")) != 2:
            errors.append(f"Key '{k}' should be in 'chapter.section' format")
        if not isinstance(v, str) or not v.strip():
            errors.append(f"Section {k}: name is empty or not a string")
        elif v.strip().lower() in _GARBAGE_NAMES:
            errors.append(f"Section {k}: name looks like a placeholder: {v!r}")
    if errors:
        raise ValueError("Section validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    return parsed


def _validate_section_subsections(parsed: dict, section_id: str) -> dict:
    """
    Prompt 3 (per-section): {"<section_id>": [{id, name, type, difficulty}, ...]}
    Enforces MIN_SUBSECTIONS_PER_SEC..MAX_SUBSECTIONS_PER_SEC range.
    """
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(f"Expected a non-empty JSON object, got: {type(parsed).__name__}")

    if section_id not in parsed:
        keys = list(parsed.keys())
        raise ValueError(
            f"Expected top-level key '{section_id}', got: {keys}. "
            f"Output must be {{'{section_id}': [...]}}."
        )

    subs = parsed[section_id]
    if not isinstance(subs, list) or not subs:
        raise ValueError(
            f"Value for '{section_id}' must be a non-empty list of subsection objects"
        )

    # ── Subsection count enforcement ──────────────────────────────────────────
    n = len(subs)
    if n > MAX_SUBSECTIONS_PER_SEC:
        raise ValueError(
            f"Section '{section_id}' has {n} subsections — maximum allowed is "
            f"{MAX_SUBSECTIONS_PER_SEC}. Reduce to between {MIN_SUBSECTIONS_PER_SEC} "
            f"and {MAX_SUBSECTIONS_PER_SEC} subsections."
        )
    if n < MIN_SUBSECTIONS_PER_SEC:
        raise ValueError(
            f"Section '{section_id}' has {n} subsections — minimum required is "
            f"{MIN_SUBSECTIONS_PER_SEC}. Generate between {MIN_SUBSECTIONS_PER_SEC} "
            f"and {MAX_SUBSECTIONS_PER_SEC} subsections."
        )

    errors = []
    for j, s in enumerate(subs):
        if not isinstance(s, dict):
            errors.append(
                f"Entry {j}: expected an object, got {type(s).__name__} ({str(s)[:60]!r})"
            )
            continue
        if not s.get("id", "").strip():
            errors.append(f"Entry {j}: missing or empty 'id'")
        name = s.get("name", "")
        if not name or not name.strip():
            errors.append(f"Entry {j}: missing or empty 'name'")
        elif name.strip().lower() in _GARBAGE_NAMES:
            errors.append(f"Entry {j}: 'name' is a placeholder value: {name!r}")

    if errors:
        raise ValueError(
            f"Subsection validation failed ({len(errors)} problems):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return parsed


# ── Subsection entry normaliser ───────────────────────────────────────────────

def _parse_subsection_list(subs: list, sec_id: str) -> list[dict]:
    result = []
    for i, s in enumerate(subs, start=1):
        if isinstance(s, dict):
            result.append({
                "id":         s.get("id",   f"{sec_id}.{i}"),
                "name":       s.get("name", f"Subsection {sec_id}.{i}"),
                "type":       s.get("type"),
                "difficulty": s.get("difficulty"),
            })
        elif isinstance(s, str):
            logger.warning(f"Subsection entry is a plain string — synthesising id: '{s}'")
            result.append({
                "id":         f"{sec_id}.{i}",
                "name":       s,
                "type":       None,
                "difficulty": None,
            })
        else:
            logger.warning(f"Unexpected subsection entry type {type(s)}: {s}")
    return result


# ── Public helpers ────────────────────────────────────────────────────────────

def get_all_subsections(skeleton: dict) -> list[dict]:
    """Flat ordered list of all subsections with their chapter_id and section_id."""
    result = []
    for ch in skeleton["chapters"]:
        for sec in ch["sections"]:
            for sub in sec["subsections"]:
                result.append({
                    "id":         sub["id"],
                    "name":       sub["name"],
                    "type":       sub.get("type"),
                    "difficulty": sub.get("difficulty"),
                    "chapter_id": ch["id"],
                    "section_id": sec["id"],
                })
    return result


def fmt_skeleton_condensed(skeleton: dict) -> str:
    """
    Compact flat-text representation of the full skeleton.
    ~8× smaller than json.dumps(skeleton, indent=2).
    Used in all Phase 3 prompts instead of raw JSON.

    Example output:
        Chapter 1: Thermodynamic Systems
          1.1 System Types and Boundaries
            1.1.1 Open Systems [theory, foundational]
            1.1.2 Closed Systems [theory, foundational]
    """
    lines = []
    for ch in skeleton["chapters"]:
        lines.append(f"Chapter {ch['id']}: {ch['name']}")
        for sec in ch["sections"]:
            lines.append(f"  {sec['id']} {sec['name']}")
            for sub in sec.get("subsections", []):
                typ  = sub.get("type") or ""
                diff = sub.get("difficulty") or ""
                tag  = f" [{typ}, {diff}]" if (typ or diff) else ""
                lines.append(f"    {sub['id']} {sub['name']}{tag}")
    return "\n".join(lines)


# ── Checkpoint ────────────────────────────────────────────────────────────────

def _save(skeleton: dict):
    write_file(SKELETON_PATH, json.dumps(skeleton, indent=2))


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_chapter_list(chapters: list) -> str:
    """All chapter names — used as the full scope overview."""
    return "\n".join(f'{ch["id"]}. {ch["name"]}' for ch in chapters)


def _fmt_section_list(sections: list) -> str:
    """All sections in the current chapter."""
    return "\n".join(f'{s["id"]}. {s["name"]}' for s in sections)


def _fmt_previous_chapter_sections(skeleton: dict, current_ch_idx: int) -> str:
    """Section names of the immediately preceding chapter only."""
    if current_ch_idx == 0:
        return "None — this is the first chapter."
    prev_ch = skeleton["chapters"][current_ch_idx - 1]
    lines   = [f"Chapter {prev_ch['id']}: {prev_ch['name']}"]
    for sec in prev_ch["sections"]:
        lines.append(f"  {sec['id']}. {sec['name']}")
    return "\n".join(lines)


def _fmt_subsections_so_far(subsections_so_far: dict) -> str:
    """
    Subsection names (not full detail) for sections already done in this chapter.
    Used as the current_chapter_subsections_so_far variable in Prompt 3.
    """
    if not subsections_so_far:
        return "None — this is the first section of this chapter."
    lines = []
    for sec_id, subs in subsections_so_far.items():
        lines.append(f"Section {sec_id}:")
        for sub in subs:
            lines.append(f"  {sub['id']}. {sub['name']}")
    return "\n".join(lines)


def _fmt_prev_sections(skeleton: dict, sections_done: set) -> str:
    """Section names for the last LOOKBACK_CHAPTERS completed chapters."""
    done_chapters = [ch for ch in skeleton["chapters"] if ch["id"] in sections_done]
    recent        = {ch["id"] for ch in done_chapters[-LOOKBACK_CHAPTERS:]}
    lines = []
    for ch in skeleton["chapters"]:
        if ch["id"] not in sections_done:
            continue
        if ch["id"] in recent:
            lines.append(f"Chapter {ch['id']}: {ch['name']}")
            for s in ch["sections"]:
                lines.append(f"  {s['id']}. {s['name']}")
        else:
            lines.append(f"Chapter {ch['id']}: {ch['name']}  [sections omitted for brevity]")
    return "\n".join(lines) if lines else "None yet."