"""Builds the LLM every agent uses: gpt-6-luna routed through Portkey.

It uses the OpenAI *Responses* API (/v1/responses). gpt-6-luna refuses tool calls on
/v1/chat/completions while reasoning is on, and most agents here need tools.

Only one model is allowed in MGT 409, so it is fixed here and the code refuses to start
if .env asks for anything else.

.env loading order (the first value found wins):
  1. <repo>/.env         - your own copy
  2. <repo>/../.env      - where graders put theirs, one folder above the repo
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")  # does not override anything already set

MODEL_NAME = "gpt-6-luna"  # the only model allowed in this course
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"


def build_model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PORTKEY_API_KEY is missing. Copy .env.example to .env (here or one folder up) "
            "and add your Portkey key."
        )
    requested = os.getenv("PORTKEY_MODEL", MODEL_NAME)
    if requested != MODEL_NAME:
        raise RuntimeError(f"Only {MODEL_NAME} is allowed; .env asks for {requested!r}.")
    provider = OpenAIProvider(
        api_key=api_key,
        base_url=os.getenv("PORTKEY_BASE_URL", PORTKEY_BASE_URL),
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=provider)


def model_ready() -> tuple[bool, str]:
    """For the health check: can we build the model? Never makes an API call."""
    try:
        build_model()
        return True, MODEL_NAME
    except RuntimeError as e:
        return False, str(e)
