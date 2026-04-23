#!/usr/bin/env python3
"""Import parsing helpers for token, session JSON, and CPA JSON."""

from __future__ import annotations

import hashlib
import json

from app.models import AccountRecord, AccountSourceKind, BrowserProfile


class ImportedAccountSeed:
    """Normalized import seed extracted from one operator-supplied payload."""

    def __init__(
        self,
        name: str,
        access_token: str,
        source_kind: AccountSourceKind,
        browser_profile: BrowserProfile,
    ) -> None:
        self.name = name
        self.access_token = access_token
        self.source_kind = source_kind
        self.browser_profile = browser_profile


def derive_account_name(access_token: str) -> str:
    """Derives a stable synthetic account name from an imported access token."""
    digest = hashlib.sha1(access_token.encode()).hexdigest()
    return f"acct_{digest[:12]}"


def parse_access_token_seed(raw: str) -> ImportedAccountSeed:
    access_token = raw.strip()
    if not access_token:
        raise ValueError("access token is empty")
    return ImportedAccountSeed(
        name=derive_account_name(access_token),
        access_token=access_token,
        source_kind=AccountSourceKind.TOKEN,
        browser_profile=BrowserProfile(),
    )


def parse_session_seed(raw: str) -> ImportedAccountSeed:
    value = json.loads(raw)
    access_token = value.get("accessToken", "")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("session JSON missing accessToken")
    access_token = access_token.strip()
    session_token = value.get("sessionToken")
    if not isinstance(session_token, str):
        session_token = None
    else:
        session_token = session_token.strip() or None
    browser_profile = BrowserProfile(
        session_token=session_token,
        user_agent=None,
        impersonate_browser="edge",
    )
    return ImportedAccountSeed(
        name=derive_account_name(access_token),
        access_token=access_token,
        source_kind=AccountSourceKind.SESSION_JSON,
        browser_profile=browser_profile,
    )


def build_account_record(seed: ImportedAccountSeed) -> AccountRecord:
    """Converts one normalized import seed into an account record with active defaults."""
    return AccountRecord(
        name=seed.name,
        access_token=seed.access_token,
        source_kind=seed.source_kind,
        status="active",
        request_max_concurrency=2,
        browser_profile_json=seed.browser_profile.model_dump_json(),
    )
