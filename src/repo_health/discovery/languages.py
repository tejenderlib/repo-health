"""Extension-based language detection (Stage 3, Task 3).

Maps lowercase file extensions to language names using an explicit,
minimal table. Unknown or missing extensions return None (UNKNOWN
evidence), never a guessed language. Only the final extension is
considered: ``archive.tar.gz`` is unknown.
"""

from __future__ import annotations

import os

from repo_health.core.exceptions import ValidationError

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".sh": "shell",
    ".bash": "shell",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".markdown": "markdown",
}


def detect_language(rel_posix_path: str) -> str | None:
    """Return the language for a path, or None when unknown."""
    if not isinstance(rel_posix_path, str):
        raise ValidationError(f"path must be a string, got {rel_posix_path!r}")
    _, extension = os.path.splitext(rel_posix_path)
    if extension == "":
        return None
    return EXTENSION_MAP.get(extension.lower())
