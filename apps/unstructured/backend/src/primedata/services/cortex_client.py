"""
Cortex API client for LLM-powered text processing.

Uses Azure AD client credentials to authenticate against the Cortex gateway
and call hosted models for noise reduction and content cleaning.
"""

import os
from typing import Optional

import requests

from primedata.indexing.azure_openai_auth import get_cortex_token_provider
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

CORTEX_API_BASE_URL = os.getenv("CORTEX_API_URL", "https://chat.lilly.com")
CORTEX_MODEL_ID = os.getenv("CORTEX_MODEL_ID", "mm-business-meta-generator-consolidated-model")


def call_cortex_model(prompt: str, model_context: str = "") -> Optional[str]:
    """
    Call the Cortex API with a prompt and return the response.

    :param prompt: The prompt text to send.
    :param model_context: Additional context for the model (default empty).
    :return: Response text from the model, or None on failure.
    """
    try:
        provider = get_cortex_token_provider()
        headers = provider.get_auth_header()
        headers["Content-Type"] = "application/json"
        headers["accept"] = "application/json"

        url = f"{CORTEX_API_BASE_URL}/model/ask-with-custom-prompt/{CORTEX_MODEL_ID}"
        payload = {
            "prompt": prompt,
            "model_context": model_context,
            "default_knowledge": True,
        }

        logger.info(f"Calling Cortex API | model={CORTEX_MODEL_ID}, prompt_length={len(prompt)}")

        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()

        result = response.json()
        logger.info(f"  Cortex API response received | status={response.status_code}, result={result}")

        return result

    except ValueError as e:
        logger.warning(f"Cortex credentials not configured: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Cortex API call failed: {e}", exc_info=True)
        return None
