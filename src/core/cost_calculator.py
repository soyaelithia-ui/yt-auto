"""Cost calculation utilities for multi-provider LLM token burn."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Pricing per million tokens (input / output / cached)
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Gemini 2.5 / 2.0 Flash
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "cached": 0.0375},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cached": 0.025},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "cached": 0.01875},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00, "cached": 0.3125},
    "gemini-2.0-pro": {"input": 1.50, "output": 6.00, "cached": 0.375},
    # Grok / Antigravity default
    "grok-2": {"input": 2.00, "output": 10.00, "cached": 0.50},
    "default": {"input": 0.15, "output": 0.60, "cached": 0.0375},
}


class CostCalculator:
    """Calculates estimated USD cost for model inference."""

    @classmethod
    def calculate_cost(
        cls,
        model: str | None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
    ) -> float:
        """Compute estimated USD cost based on token counts and model pricing."""
        m_key = str(model).lower() if model else "default"

        pricing = MODEL_PRICING.get("default", {"input": 0.15, "output": 0.60, "cached": 0.0375})
        for pattern, rates in MODEL_PRICING.items():
            if pattern in m_key:
                pricing = rates
                break

        input_rate = pricing.get("input", 0.15) / 1_000_000.0
        output_rate = pricing.get("output", 0.60) / 1_000_000.0
        cached_rate = pricing.get("cached", 0.0375) / 1_000_000.0

        active_prompt = max(0, prompt_tokens - cached_tokens)
        cost = (
            (active_prompt * input_rate)
            + (cached_tokens * cached_rate)
            + (completion_tokens * output_rate)
        )
        return round(cost, 6)
