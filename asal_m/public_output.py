"""Safe-by-default serialization helpers for shareable ASAL-M output.

Runtime code may use absolute paths to do work. Persisted reports should not
publish the host directory layout merely because a user ran them locally.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import numpy as np

_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_QUOTED_ABSOLUTE_PATH = re.compile(
    r"(?P<quote>['\"`])"
    r"(?P<path>(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|tmp)/).*?)"  # public-scan: host-pattern
    r"(?P=quote)",
    re.IGNORECASE,
)
_EMBEDDED_WINDOWS_FILE_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\)"  # public-scan: host-pattern
    r"[^'\"`<>|\r\n]*?[\\/][^\\/'\"`<>|\r\n]*?\.[A-Za-z0-9]{1,16}"  # public-scan: host-pattern
    r"(?=$|[\s,;:)\]}])"
    # public-scan: host-pattern
)
_EMBEDDED_WINDOWS_SPACED_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\)"  # public-scan: host-pattern
    r"[^'\"`<>|\r\n,;:)\]}]+?"  # public-scan: host-pattern
    r"(?="  # public-scan: host-pattern
    r"$|[,;:)\]}]|"  # public-scan: host-pattern
    r"\s+(?:and|then|before|after|while)\s+(?=[^\\/'\"`<>|\r\n]*$)"  # public-scan: host-pattern
    r")",
    re.IGNORECASE,
)
_EMBEDDED_WINDOWS_COMPACT_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\)[^\s'\"`<>|]+"  # public-scan: host-pattern
)
_EMBEDDED_POSIX_HOST_FILE_PATH = re.compile(
    r"(?<![A-Za-z0-9:/])/(?:Users|home|tmp)/"
    r"[^'\"`<>|\r\n]*?/[^/'\"`<>|\r\n]*?\.[A-Za-z0-9]{1,16}"
    r"(?=$|[\s,;:)\]}])",  # public-scan: host-pattern
    re.IGNORECASE,
)
_EMBEDDED_POSIX_HOST_SPACED_PATH = re.compile(
    r"(?<![A-Za-z0-9:/])/(?:Users|home|tmp)/"  # public-scan: host-pattern
    r"[^'\"`<>|\r\n,;:)\]}]+?"  # public-scan: host-pattern
    r"(?="  # public-scan: host-pattern
    r"$|[,;:)\]}]|"  # public-scan: host-pattern
    r"\s+(?:and|then|before|after|while)\s+(?=[^/'\"`<>|\r\n]*$)"  # public-scan: host-pattern
    r")",
    re.IGNORECASE,
)
_EMBEDDED_POSIX_HOST_COMPACT_PATH = re.compile(
    r"(?<![A-Za-z0-9:/])/(?:Users|home|tmp)/[^\s'\"`<>|]+",  # public-scan: host-pattern
    re.IGNORECASE,
)


def utc_timestamp() -> str:
    """Return a second-precision UTC timestamp with an explicit ``Z`` suffix."""
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def public_path(value: str | Path, *, base_dir: str | Path | None = None) -> str:
    """Render a path without exposing an absolute host root.

    Paths inside ``base_dir`` are emitted relative to it with POSIX separators.
    Paths outside that boundary retain only their leaf name.
    """
    base = _resolved_base(base_dir)
    raw = str(value)

    if _is_windows_absolute(raw):
        return _public_windows_path(raw, base)
    if raw.startswith("/"):
        return _public_posix_path(raw, base)

    path = Path(raw)
    candidates = (path, base / path)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            return resolved.relative_to(base).as_posix()
        except (OSError, ValueError):
            continue
    return _path_leaf(raw)


def sanitize_public_string(value: str, *, base_dir: str | Path | None = None) -> str:
    """Redact a string when the complete value is an absolute host path."""
    if not value:
        return value
    if _is_windows_absolute(value) or value.startswith("/"):
        return public_path(value, base_dir=base_dir)
    value = _QUOTED_ABSOLUTE_PATH.sub(
        lambda match: (
            f"{match.group('quote')}"
            f"{_path_leaf(match.group('path'))}"
            f"{match.group('quote')}"
        ),
        value,
    )
    value = _EMBEDDED_WINDOWS_FILE_PATH.sub(
        lambda match: _path_leaf(match.group(0)),
        value,
    )
    value = _EMBEDDED_WINDOWS_SPACED_PATH.sub(
        lambda match: _path_leaf(match.group(0).rstrip()),
        value,
    )
    value = _EMBEDDED_WINDOWS_COMPACT_PATH.sub(
        lambda match: _path_leaf(match.group(0)),
        value,
    )
    value = _EMBEDDED_POSIX_HOST_FILE_PATH.sub(
        lambda match: _path_leaf(match.group(0)),
        value,
    )
    value = _EMBEDDED_POSIX_HOST_SPACED_PATH.sub(
        lambda match: _path_leaf(match.group(0).rstrip()),
        value,
    )
    return _EMBEDDED_POSIX_HOST_COMPACT_PATH.sub(
        lambda match: _path_leaf(match.group(0)),
        value,
    )


def to_public_data(payload: Any, *, base_dir: str | Path | None = None) -> Any:
    """Recursively convert values into safe, JSON/YAML-compatible data."""
    if isinstance(payload, Path):
        return public_path(payload, base_dir=base_dir)
    if isinstance(payload, dict):
        public: dict[str, Any] = {}
        for key, value in payload.items():
            cleaned_key = sanitize_public_string(str(key), base_dir=base_dir)
            if cleaned_key in public:
                raise ValueError(
                    "public key sanitization produced a duplicate mapping key"
                )
            public[cleaned_key] = to_public_data(value, base_dir=base_dir)
        return public
    if isinstance(payload, (list, tuple)):
        return [to_public_data(value, base_dir=base_dir) for value in payload]
    if isinstance(payload, np.ndarray):
        return payload.tolist()
    if isinstance(payload, (np.floating, np.integer)):
        return payload.item()
    if isinstance(payload, datetime):
        aware = (
            payload.replace(tzinfo=timezone.utc)
            if payload.tzinfo is None
            else payload.astimezone(timezone.utc)
        )
        return aware.isoformat(timespec="seconds").replace("+00:00", "Z")
    if isinstance(payload, date):
        return payload.isoformat()
    if isinstance(payload, str):
        return sanitize_public_string(payload, base_dir=base_dir)
    return payload


def _resolved_base(base_dir: str | Path | None) -> Path:
    base = Path.cwd() if base_dir is None else Path(base_dir)
    try:
        return base.resolve()
    except OSError:
        return base


def _is_windows_absolute(value: str) -> bool:
    return bool(_WINDOWS_ABSOLUTE.match(value)) or value.startswith(("\\", "//"))


def _public_windows_path(value: str, base: Path) -> str:
    candidate = PureWindowsPath(value)
    base_text = str(base)
    if _is_windows_absolute(base_text):
        try:
            relative = candidate.relative_to(PureWindowsPath(base_text))
            return PurePosixPath(*relative.parts).as_posix()
        except (ValueError, OSError):
            pass

    # On Windows, pathlib can compare native absolute paths more accurately.
    native = Path(value)
    if native.is_absolute():
        try:
            return native.resolve().relative_to(base).as_posix()
        except (OSError, ValueError):
            pass
    return candidate.name or "external_path"


def _public_posix_path(value: str, base: Path) -> str:
    candidate = PurePosixPath(value)
    base_text = base.as_posix()
    if base_text.startswith("/"):
        try:
            return candidate.relative_to(PurePosixPath(base_text)).as_posix()
        except ValueError:
            pass
    return candidate.name or "external_path"


def _path_leaf(value: str) -> str:
    normalized = value.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] or "external_path"
