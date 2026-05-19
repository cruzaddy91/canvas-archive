"""Validate profile flags for production-style archives (post-UAT lockdown)."""

from __future__ import annotations

from typing import Any


def validate_profile_security_flags(profile: dict[str, Any]) -> None:
    """Raise ``SystemExit`` when mutually inconsistent external-starter flags are set.

    Broad HTTPS starters for the course-home table require ``developer_mode`` so UAT
    discovery cannot accidentally ship as production configuration.
    """
    if bool(profile.get("developer_mode")):
        return
    if profile.get("course_home_external_starters_allow_any_https_host"):
        raise SystemExit(
            "profile lockdown: course_home_external_starters_allow_any_https_host "
            "requires developer_mode: true. Remove the allow-any-https flag or enable "
            "developer_mode only while actively discovering hosts for a course profile."
        )
