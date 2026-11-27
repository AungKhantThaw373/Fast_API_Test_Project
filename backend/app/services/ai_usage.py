"""AI usage ledger and monthly budget checks.

Every successful model call writes one row. Local Ollama calls cost zero, so a
fresh story with a zero budget remains fully usable offline; cloud calls are
refused before they start unless the writer set a positive budget.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.logging_config import get_logger
from app.models.story_models import Story
from app.models.wiki_models import AIUsage
from app.services.ai_settings import load_ai_config

logger = get_logger("ai_usage")

LOCAL_PROVIDERS = {"ollama"}

# Coarse public list prices, USD per million tokens. Unknown cloud models use a
# conservative fallback so a budget cannot be silently exceeded by a new model.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
}
FALLBACK_PRICE = (1.00, 3.00)


def price_for(provider: str, model: str) -> tuple[float, float]:
    if provider in LOCAL_PROVIDERS:
        return (0.0, 0.0)
    lowered = model.casefold()
    for prefix, price in PRICES_PER_MTOK.items():
        if prefix in lowered:
            return price
    return FALLBACK_PRICE


def estimate_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> Decimal:
    input_price, output_price = price_for(provider, model)
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    return Decimal(str(round(cost, 6)))


def estimate_scan_tokens(chars: int) -> tuple[int, int]:
    """Rough pre-flight estimate: four characters per input token."""
    input_tokens = max(1, chars // 4)
    output_tokens = min(1200, max(200, input_tokens // 4))
    return input_tokens, output_tokens


def month_bounds(month: str | None = None) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if month:
        try:
            year, month_number = (int(part) for part in month.split("-", 1))
            now = now.replace(year=year, month=month_number)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Month must look like 2026-11.") from exc
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = calendar.monthrange(start.year, start.month)[1]
    end = start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    return start, end


async def record_ai_usage(
    *,
    user_id: UUID,
    story_id: UUID | None,
    purpose: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
) -> None:
    """Best-effort ledger write: never turn a successful answer into an error."""
    try:
        async with async_session() as session:
            session.add(
                AIUsage(
                    user_id=user_id,
                    story_id=story_id,
                    purpose=purpose[:200],
                    provider=provider[:60],
                    model=model[:200],
                    input_tokens=max(0, input_tokens),
                    output_tokens=max(0, output_tokens),
                    cost_estimate=estimate_cost(provider, model, input_tokens, output_tokens),
                    duration_ms=max(0, duration_ms),
                )
            )
            await session.commit()
    except Exception as exc:  # pragma: no cover - a ledger must not break generation
        logger.warning(
            "[ai_usage] write failed purpose=%s provider=%s error=%s",
            purpose,
            provider,
            type(exc).__name__,
        )


async def month_spend(
    session: AsyncSession, story_id: UUID, *, month: str | None = None
) -> Decimal:
    start, end = month_bounds(month)
    total = await session.scalar(
        select(func.coalesce(func.sum(AIUsage.cost_estimate), 0)).where(
            AIUsage.story_id == story_id,
            AIUsage.created_at >= start,
            AIUsage.created_at <= end,
        )
    )
    return Decimal(str(total or 0))


async def usage_summary(
    session: AsyncSession, story_id: UUID, *, month: str | None = None
) -> dict[str, Any]:
    start, end = month_bounds(month)
    rows = (
        await session.execute(
            select(
                AIUsage.purpose,
                AIUsage.provider,
                AIUsage.model,
                func.count(AIUsage.id),
                func.coalesce(func.sum(AIUsage.input_tokens), 0),
                func.coalesce(func.sum(AIUsage.output_tokens), 0),
                func.coalesce(func.sum(AIUsage.cost_estimate), 0),
                func.coalesce(func.avg(AIUsage.duration_ms), 0),
            )
            .where(
                AIUsage.story_id == story_id,
                AIUsage.created_at >= start,
                AIUsage.created_at <= end,
            )
            .group_by(AIUsage.purpose, AIUsage.provider, AIUsage.model)
            .order_by(func.sum(AIUsage.cost_estimate).desc(), AIUsage.purpose)
        )
    ).all()
    calls = sum(int(row[3]) for row in rows)
    input_tokens = sum(int(row[4]) for row in rows)
    output_tokens = sum(int(row[5]) for row in rows)
    spent = sum((Decimal(str(row[6])) for row in rows), Decimal("0"))
    return {
        "month": start.strftime("%Y-%m"),
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "spent_usd": float(spent),
        "by_purpose": [
            {
                "purpose": row[0],
                "provider": row[1],
                "model": row[2],
                "calls": int(row[3]),
                "input_tokens": int(row[4]),
                "output_tokens": int(row[5]),
                "cost_usd": float(Decimal(str(row[6]))),
                "average_duration_ms": int(row[7]),
            }
            for row in rows
        ],
    }


async def check_budget(
    session: AsyncSession,
    story: Story,
    user_id: UUID,
    *,
    chars: int,
    purpose: str,
) -> dict[str, Any]:
    """Refuse a cloud call before spending when it would exceed the month budget."""
    config = await load_ai_config(user_id)
    input_tokens, output_tokens = estimate_scan_tokens(chars)
    estimated = estimate_cost(config.provider, config.model, input_tokens, output_tokens)
    budget = Decimal(str(story.monthly_ai_budget or 0))
    spent = await month_spend(session, story.id)
    if estimated > 0 and (budget <= 0 or spent + estimated > budget):
        limit = f"{budget:.2f} USD" if budget > 0 else "no cloud budget (local-only)"
        raise HTTPException(
            status_code=402,
            detail=(
                f"{purpose} would cost about {float(estimated):.4f} USD, but this story has {limit}. "
                "Raise the monthly AI budget in story settings, or keep using local Ollama."
            ),
        )
    return {
        "provider": config.provider,
        "model": config.model,
        "estimated_cost_usd": float(estimated),
        "spent_usd": float(spent),
        "budget_usd": float(budget),
        "remaining_usd": float(budget - spent) if budget > 0 else 0.0,
    }
