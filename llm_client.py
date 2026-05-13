import http.client
import json
import logging

from config import API_HOST, API_PORT, API_KEY, MAX_TOKENS, TEMPERATURE

logger = logging.getLogger(__name__)


def call_llm(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
) -> str:
    """Single-turn call. Convenience wrapper around call_llm_messages."""
    messages = [{"role": "user", "content": user_prompt}]
    return call_llm_messages(model, system_prompt, messages, max_tokens, temperature)


def call_llm_messages(
    model: str,
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
) -> str:
    """
    Multi-turn call. `messages` is a list of {"role": ..., "content": ...} dicts.
    Returns the assistant message content as a plain string.
    Raises RuntimeError on HTTP or API errors.
    """
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    })

    headers = {
        "Content-Type": "application/json",
        "Authorization": API_KEY,
    }

    logger.debug(f"Calling model={model}  turns={len(messages)}  max_tokens={max_tokens}")

    conn = http.client.HTTPConnection(API_HOST, API_PORT)
    conn.request("POST", "/v1/chat/completions", payload, headers)
    res  = conn.getresponse()
    body = res.read().decode("utf-8")
    conn.close()

    if res.status != 200:
        raise RuntimeError(f"LLM API returned {res.status}: {body}")

    data = json.loads(body)
    return data["choices"][0]["message"]["content"]