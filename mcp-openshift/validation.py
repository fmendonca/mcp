"""Input validation helpers for resource names and env-driven config."""

import os
import re
from typing import List

from fastapi import HTTPException

_SAFE_NAME_RE = re.compile(r"^[^\x00/\\]{1,253}$")
_DNS_LABEL_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")


def validated_name(name: str) -> str:
    if not name or not _SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid resource name: {name!r}")
    return name


def validated_dns_label(name: str, resource_type: str) -> str:
    validated_name(name)
    if not _DNS_LABEL_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid {resource_type} name: {name!r}. Use a DNS label: "
                "lowercase letters, numbers and hyphens only, up to 63 "
                "characters, starting and ending with a letter or number."
            ),
        )
    return name


def csv_env(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]
