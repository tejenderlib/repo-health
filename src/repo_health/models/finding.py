"""Finding model and stable finding-identity algorithm (Stage 1 contract).

Identity algorithm v1 (``rh-finding-id-v1``):

* Inputs: analyzer id, rule id, canonical repo-relative path, locator,
  fingerprint. Each component is stripped of surrounding whitespace.
* The path is canonicalized by :func:`canonicalize_repo_path` (POSIX
  separators, no leading ``./``, no absolute paths, no ``..`` escapes).
* The canonical string is::

      rh-finding-id-v1|<analyzer>|<rule>|<path>|<locator>|<fingerprint>

* The finding id is ``rh1-<first 16 hex chars of SHA-256(canonical)>``.

The id therefore depends only on stable rule evidence: never on wall-clock
time, random values, discovery order, or absolute checkout paths.

Guidance for analyzers (enforced by convention, tested in Stage 4):

* ``locator`` locates the occurrence within the file (``""`` for
  file-level rules; otherwise ``L<start>`` or ``L<start>-L<end>``).
* ``fingerprint`` distinguishes separate occurrences of the same rule at
  the same location (e.g. a dependency name). It must never contain
  secret or credential material.
* ``evidence`` must describe the observation without reproducing secrets.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from repo_health.core.exceptions import ValidationError

IDENTITY_ALGORITHM = "rh-finding-id-v1"
IDENTITY_PREFIX = "rh1-"
IDENTITY_RE = re.compile(r"rh1-[0-9a-f]{16}")
IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]{0,63}")
_ABSOLUTE_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class Severity(StrEnum):
    """Finding severity. Describes an established finding, not uncertainty."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Numeric rank for deterministic severity ordering (higher is worse)."""
        return {
            Severity.CRITICAL: 5,
            Severity.HIGH: 4,
            Severity.MEDIUM: 3,
            Severity.LOW: 2,
            Severity.INFO: 1,
        }[self]


def canonicalize_repo_path(path: str) -> str:
    """Return the canonical repo-relative form of ``path``.

    ``""`` is allowed and means the finding has no file location.
    Otherwise the result uses POSIX separators and is relative to the
    repository root. Absolute paths, drive-qualified paths, and paths
    escaping the root via ``..`` are rejected.
    """
    if path == "":
        return ""
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    normalized = posixpath.normpath(cleaned)
    if (
        not normalized
        or normalized == "."
        or normalized.startswith("/")
        or _ABSOLUTE_DRIVE_RE.match(normalized) is not None
        or normalized == ".."
        or normalized.startswith("../")
    ):
        raise ValidationError(f"path is not a valid repo-relative path: {path!r}")
    if "/../" in normalized:
        raise ValidationError(f"path escapes the repository root: {path!r}")
    return normalized


def compute_finding_id(
    analyzer: str,
    rule: str,
    path: str = "",
    locator: str = "",
    fingerprint: str = "",
) -> str:
    """Compute the stable v1 finding id for the given identity components."""
    canonical = "|".join(
        (
            IDENTITY_ALGORITHM,
            analyzer.strip(),
            rule.strip(),
            canonicalize_repo_path(path),
            locator.strip(),
            fingerprint.strip(),
        )
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{IDENTITY_PREFIX}{digest[:16]}"


def validate_identifier(kind: str, value: str) -> str:
    cleaned = value.strip()
    if IDENTIFIER_RE.fullmatch(cleaned) is None:
        raise ValidationError(
            f"{kind} must match {IDENTIFIER_RE.pattern}, got {value!r}"
        )
    return cleaned


def _require_text(kind: str, value: str) -> str:
    if value.strip() == "":
        raise ValidationError(f"{kind} must not be blank")
    return value


@dataclass(frozen=True)
class Finding:
    """An issue or observation supported by analysis evidence."""

    id: str = ""
    analyzer: str = ""
    rule: str = ""
    title: str = ""
    description: str = ""
    severity: Severity = Severity.INFO
    path: str = ""
    locator: str = ""
    fingerprint: str = ""
    evidence: str = ""
    recommendation: str = ""

    def __post_init__(self) -> None:
        analyzer = validate_identifier("analyzer", self.analyzer)
        rule = validate_identifier("rule", self.rule)
        title = _require_text("title", self.title)
        description = _require_text("description", self.description)
        evidence = _require_text("evidence", self.evidence)
        if not isinstance(self.severity, Severity):
            raise ValidationError(
                f"severity must be a Severity member, got {self.severity!r}"
            )
        path = canonicalize_repo_path(self.path)
        locator = self.locator.strip()
        fingerprint = self.fingerprint.strip()
        if locator != "" and path == "":
            raise ValidationError("locator requires a file path")
        finding_id = self.id.strip()
        if finding_id == "":
            finding_id = compute_finding_id(analyzer, rule, path, locator, fingerprint)
        else:
            if IDENTITY_RE.fullmatch(finding_id) is None:
                raise ValidationError(
                    f"id must match {IDENTITY_RE.pattern}, got {self.id!r}"
                )
            expected = compute_finding_id(analyzer, rule, path, locator, fingerprint)
            if finding_id != expected:
                raise ValidationError(
                    "id does not match the finding identity components"
                )
        object.__setattr__(self, "analyzer", analyzer)
        object.__setattr__(self, "rule", rule)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "locator", locator)
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(self, "recommendation", self.recommendation.strip())
        object.__setattr__(self, "id", finding_id)

    def sort_key(self) -> str:
        """Stable deterministic ordering key."""
        return self.id

    def to_dict(self) -> dict[str, str]:
        """Serialize with fixed key order for stable output."""
        return {
            "id": self.id,
            "analyzer": self.analyzer,
            "rule": self.rule,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "path": self.path,
            "locator": self.locator,
            "fingerprint": self.fingerprint,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> Finding:
        """Deserialize, raising ValidationError on missing or invalid fields."""
        try:
            return cls(
                id=str(data["id"]),
                analyzer=str(data["analyzer"]),
                rule=str(data["rule"]),
                title=str(data["title"]),
                description=str(data["description"]),
                severity=Severity(str(data["severity"])),
                path=str(data["path"]),
                locator=str(data["locator"]),
                fingerprint=str(data["fingerprint"]),
                evidence=str(data["evidence"]),
                recommendation=str(data["recommendation"]),
            )
        except KeyError as exc:
            raise ValidationError(f"finding field missing: {exc}") from exc
        except ValueError as exc:
            raise ValidationError(f"invalid finding data: {exc}") from exc
