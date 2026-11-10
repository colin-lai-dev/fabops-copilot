"""USD per 1M tokens (input, output). Source: third-party summaries of official price pages,
late Oct 2026 (ADR-0008). Re-check the official pages before any paid run.
Unknown models cost 0 and are flagged in the usage log.
"""

PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),  # prompts <= 100K tokens
    "claude-sonnet-5-5": (2.00, 10.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gemini-2.5-flash": (0.30, 2.50),
    # Official pricing page (aistudio.google.com/docs/pricing), checked 2026-11-10: standard
    # paid tier through 2026-12-31, output includes thinking; doubles from 2027-01-01.
    "gemini-3.6-flash": (0.75, 3.75),
}

LOCAL_PROVIDERS = {"ollama"}


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float | None:
    if provider in LOCAL_PROVIDERS:
        return 0.0
    price = PRICES.get(model)
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
