import json
import os
import re
import logging

logger = logging.getLogger(__name__)


# ── Raw JSON response parsing ─────────────────────────────────────────────────

def parse_json_response(text: str) -> dict | list:
    """
    Parse a model response that is supposed to be a bare JSON object or array.
    Strips markdown code fences (```json...```) and any preamble/postamble
    by finding the first { or [ and its matching closing bracket.
    Raises ValueError on failure.
    """
    text = text.strip()

    # Strip markdown code fences the model sometimes wraps around JSON
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    # Find the first opening bracket
    start = -1
    open_char, close_char = None, None
    for idx, ch in enumerate(text):
        if ch == "{":
            open_char, close_char, start = "{", "}", idx
            break
        if ch == "[":
            open_char, close_char, start = "[", "]", idx
            break

    if start == -1:
        raise ValueError(f"No JSON object or array found in response:\n{text[:300]}")

    # Walk forward to find the matching closing bracket
    depth = 0
    in_string = False
    escape_next = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                json_str = text[start : idx + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"JSON parse failed: {e}\nExtracted:\n{json_str[:300]}"
                    )

    raise ValueError(f"Unmatched brackets in response:\n{text[:300]}")


# ── XML-style block parsing ───────────────────────────────────────────────────

def parse_block(text: str, tag: str) -> str:
    """
    Extract content between <TAG>...</TAG>.
    Returns empty string if the tag is not found.
    """
    pattern = rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        logger.warning(f"parse_block: tag <{tag}> not found in response")
        return ""
    return match.group(1).strip()


# ── Registry / Concept Index delta merge ─────────────────────────────────────

def apply_delta(delta_text: str, file_path: str, tag: str):
    """
    Find all  <<TAG: key>> ... <</TAG>>  blocks in delta_text.
    For each:
      - if the key already exists in file_path → replace the entire block
      - otherwise → append it
    Works identically for SYMBOL (registry) and CONCEPT (concept index).
    """
    with open(file_path, "r") as f:
        content = f.read()

    entry_pattern = rf"<<{tag}: ([^>]+)>>(.*?)<</{tag}>>"
    new_entries = re.findall(entry_pattern, delta_text, re.DOTALL)

    if not new_entries:
        logger.warning(f"apply_delta: no <<{tag}>> entries found in delta")
        return

    for key, body in new_entries:
        full_entry   = f"<<{tag}: {key}>>{body}<</{tag}>>"
        existing_pat = rf"<<{tag}: {re.escape(key)}>>(.*?)<</{tag}>>"
        if re.search(existing_pat, content, re.DOTALL):
            content = re.sub(existing_pat, lambda m, e=full_entry: e, content, flags=re.DOTALL)
            logger.debug(f"apply_delta: updated {tag} '{key}'")
        else:
            content += "\n\n" + full_entry
            logger.debug(f"apply_delta: appended {tag} '{key}'")

    with open(file_path, "w") as f:
        f.write(content)


# ── Simple file I/O ───────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    """Return file contents, or empty string if file does not exist."""
    if not os.path.exists(path):
        return ""
    with open(path, "r") as f:
        return f.read()


def write_file(path: str, content: str):
    """Write content to path, creating parent directories as needed."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
