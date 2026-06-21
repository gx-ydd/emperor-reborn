from __future__ import annotations

import os

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.alibaba import AlibabaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from emperor_reborn.config import Settings


def build_model(settings: Settings):
    """Build the Pydantic AI model from local settings."""

    if settings.provider == "alibaba":
        api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing DASHSCOPE_API_KEY or ALIBABA_API_KEY. "
                "Please add it to your .env file."
            )

        return OpenAIChatModel(
            settings.model,
            provider=AlibabaProvider(
                api_key=api_key,
                base_url=settings.alibaba_base_url,
            ),
        )

    if settings.provider == "openai-compatible":
        api_key = settings.openai_key
        base_url = settings.openai_base_url
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY.")
        if not base_url:
            raise RuntimeError("Missing OPENAI_BASE_URL.")

        return OpenAIChatModel(
            settings.model,
            provider=OpenAIProvider(
                api_key=api_key,
                base_url=base_url,
            ),
        )
    if settings.provider in ["local", "local-openai"]:
        if not settings.local_base_url:
            raise RuntimeError("Missing LOCAL_BASE_URL.")
        return OpenAIChatModel(
            settings.model,
            provider=OpenAIProvider(
                api_key=settings.local_api_key,
                base_url=settings.local_base_url,
            ),
        )
    raise RuntimeError(f"Unsupported EMPEROR_PROVIDER: {settings.provider}")
