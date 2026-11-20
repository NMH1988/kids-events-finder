"""Builds the chat and embedding clients for the AI provider; the only place that creates them."""

import logging
import os

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src import config

# No third-party tracing: LangSmith would receive every message, the children's age groups and
# the trip settings (LEGAL_COMPLIANCE 2.10). These are forced off whatever the environment says.
for _name in config.TRACING_ENV_OFF:
    os.environ[_name] = "false"
# At DEBUG these libraries log request bodies (the parent's message); cap them at LOG_LEVEL.
for _name in config.QUIET_LOGGERS:
    logging.getLogger(_name).setLevel(config.LOG_LEVEL)


class MissingAPIKeyError(RuntimeError):
    """The OpenRouter key is not configured."""

    def __init__(self) -> None:
        """Set a fixed message that names where the key belongs, never the key itself."""
        super().__init__(
            f"Set {config.API_KEY_NAME} in .streamlit/secrets.toml or the environment."
        )


def _require_key(api_key: str | None) -> str:
    """Return the given key or the configured one, raising when neither is set."""
    key = api_key or config.get_api_key()
    if not key:
        raise MissingAPIKeyError()
    return key


def build_chat_model(model: str | None = None, *, api_key: str | None = None) -> ChatOpenAI:
    """Build a chat client for an allowed model; settings are fixed here, never at call time."""
    model = model or config.DEFAULT_AGENT_MODEL
    if model not in config.ALLOWED_MODELS:
        raise ValueError(f"Model not allowed: {model}")
    return ChatOpenAI(
        model=model,
        base_url=config.AI_BASE_URL,
        api_key=_require_key(api_key),
        max_tokens=config.MAX_TOKENS,
        reasoning_effort=config.REASONING_EFFORT,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
        # OpenRouter's chat completions endpoint; the model name must not switch the API.
        use_responses_api=False,
    )


def build_embeddings(*, api_key: str | None = None) -> OpenAIEmbeddings:
    """Build the embeddings client for the configured embedding model on OpenRouter."""
    return OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        base_url=config.EMBEDDING_BASE_URL,
        api_key=_require_key(api_key),
        # Send raw text: by default the client sends token arrays, which OpenRouter may reject.
        check_embedding_ctx_length=False,
        request_timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
    )
