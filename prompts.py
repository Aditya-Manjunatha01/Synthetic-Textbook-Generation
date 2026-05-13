import os
import logging

from config import PROMPTS_DIR

logger = logging.getLogger(__name__)


def load_prompt(prompt_num: int, variables: dict) -> tuple[str, str]:
    """
    Load  prompt_{n}/system.md  and  prompt_{n}/user.md  from PROMPTS_DIR.
    Replace all  {{variable_name}}  placeholders with values from `variables`.
    Returns (system_text, user_text).
    """
    prompt_dir = os.path.join(PROMPTS_DIR, f"prompt_{prompt_num}")

    system_path = os.path.join(prompt_dir, "system.md")
    user_path   = os.path.join(prompt_dir, "user.md")

    with open(system_path, "r") as f:
        system = f.read()
    with open(user_path, "r") as f:
        user = f.read()

    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        system = system.replace(placeholder, str(value) if value is not None else "")
        user   = user.replace(placeholder,   str(value) if value is not None else "")

    # Warn if any unfilled placeholders remain
    import re
    remaining = re.findall(r"\{\{[^}]+\}\}", system + user)
    if remaining:
        logger.warning(f"Prompt {prompt_num}: unfilled placeholders: {remaining}")

    return system, user
