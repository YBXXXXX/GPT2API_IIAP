#!/usr/bin/env python3
"""Account candidate ordering helpers (migrated from Rust src/routing.rs)."""

from __future__ import annotations

from app.models import AccountRouteCandidate, RouteStrategy


def select_best_candidate(
    strategy: RouteStrategy, candidates: list[AccountRouteCandidate]
) -> AccountRouteCandidate | None:
    """Selects the best account candidate for the requested route strategy."""
    if not candidates:
        return None

    if strategy == RouteStrategy.FIXED:
        return candidates[0]

    # AUTO: prefer higher quota_known, then higher quota_remaining, then least recently used
    def sort_key(c: AccountRouteCandidate) -> tuple:
        return (
            int(c.quota_known),
            c.quota_remaining,
            -c.last_routed_at_ms,
        )

    return sorted(candidates, key=sort_key, reverse=True)[0]
