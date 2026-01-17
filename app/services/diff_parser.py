"""Git diff parser for extracting structured information."""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class DiffHunk:
    """Represents a single hunk in a diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str
    additions: List[str] = field(default_factory=list)
    deletions: List[str] = field(default_factory=list)


@dataclass
class DiffFile:
    """Represents a single file in a diff."""
    old_path: str
    new_path: str
    hunks: List[DiffHunk] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False
    language: Optional[str] = None

    @property
    def additions(self) -> int:
        return sum(len(h.additions) for h in self.hunks)

    @property
    def deletions(self) -> int:
        return sum(len(h.deletions) for h in self.hunks)


@dataclass
class ParsedDiff:
    """Complete parsed diff result."""
    files: List[DiffFile] = field(default_factory=list)
    raw_content: str = ""

    @property
    def total_additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        return sum(f.deletions for f in self.files)

    @property
    def languages(self) -> Set[str]:
        return {f.language for f in self.files if f.language}

    @property
    def file_count(self) -> int:
        return len(self.files)


class DiffParser:
    """Parser for unified diff format."""

    LANGUAGE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.jsx': 'javascript',
        '.java': 'java',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.c': 'c',
        '.cpp': 'cpp',
        '.cs': 'csharp',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.sql': 'sql',
        '.sh': 'bash',
        '.yml': 'yaml',
        '.yaml': 'yaml',
        '.json': 'json',
        '.html': 'html',
        '.css': 'css',
    }

    # Patterns for parsing diff headers
    # Handles both quoted paths (spaces) and unquoted paths
    FILE_HEADER_QUOTED = re.compile(r'^diff --git "a/(.+)" "b/(.+)"$')
    FILE_HEADER_UNQUOTED = re.compile(r'^diff --git a/(.+) b/(.+)$')
    HUNK_HEADER = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

    def _parse_file_header(self, line: str) -> Optional[tuple]:
        """Parse file paths from diff header, handling spaces in filenames.

        Git diff uses two formats:
        - Unquoted: diff --git a/path b/path
        - Quoted (when spaces/special chars): diff --git "a/path" "b/path"

        For unquoted paths with spaces, we use heuristics to find the split point.
        """
        # Try quoted format first (handles spaces definitively)
        match = self.FILE_HEADER_QUOTED.match(line)
        if match:
            return match.groups()

        # Try unquoted format
        match = self.FILE_HEADER_UNQUOTED.match(line)
        if not match:
            return None

        # For unquoted, the regex is greedy. We need to find the correct split.
        # The pattern "a/X b/X" means both paths should be identical or similar.
        # Strategy: find " b/" and check if paths before/after are equal
        prefix = "diff --git a/"
        if not line.startswith(prefix):
            return None

        remainder = line[len(prefix):]

        # Look for " b/" separator - try to find where old_path ends and new_path starts
        # Most common case: paths are identical (a/foo.py b/foo.py)
        split_marker = " b/"
        if split_marker not in remainder:
            return match.groups()  # Fallback to greedy match

        # Find all possible split points
        idx = 0
        candidates = []
        while True:
            pos = remainder.find(split_marker, idx)
            if pos == -1:
                break
            old_path = remainder[:pos]
            new_path = remainder[pos + len(split_marker):]
            candidates.append((old_path, new_path))
            idx = pos + 1

        if not candidates:
            return match.groups()

        # Prefer split where paths are identical (most common case)
        for old_path, new_path in candidates:
            if old_path == new_path:
                return (old_path, new_path)

        # If no identical match, prefer shortest valid paths (handles renames)
        # Return first candidate as it's most likely correct for renames
        return candidates[0]

    def parse(self, diff_content: str) -> ParsedDiff:
        """Parse a unified diff into structured format."""
        result = ParsedDiff(raw_content=diff_content)

        if not diff_content.strip():
            return result

        lines = diff_content.split('\n')
        current_file: Optional[DiffFile] = None
        current_hunk: Optional[DiffHunk] = None

        for line in lines:
            # Check for file header
            file_paths = self._parse_file_header(line)
            if file_paths:
                if current_file:
                    if current_hunk:
                        current_file.hunks.append(current_hunk)
                    result.files.append(current_file)

                old_path, new_path = file_paths
                current_file = DiffFile(
                    old_path=old_path,
                    new_path=new_path,
                    language=self._detect_language(new_path)
                )
                current_hunk = None
                continue

            # Check for hunk header
            hunk_match = self.HUNK_HEADER.match(line)
            if hunk_match and current_file:
                if current_hunk:
                    current_file.hunks.append(current_hunk)

                groups = hunk_match.groups()
                current_hunk = DiffHunk(
                    old_start=int(groups[0]),
                    old_count=int(groups[1] or 1),
                    new_start=int(groups[2]),
                    new_count=int(groups[3] or 1),
                    content=""
                )
                continue

            # Process hunk content
            if current_hunk:
                current_hunk.content += line + '\n'
                if line.startswith('+') and not line.startswith('+++'):
                    current_hunk.additions.append(line[1:])
                elif line.startswith('-') and not line.startswith('---'):
                    current_hunk.deletions.append(line[1:])

            # Check for new/deleted file
            if current_file:
                if line.startswith('new file mode'):
                    current_file.is_new = True
                elif line.startswith('deleted file mode'):
                    current_file.is_deleted = True

        # Add final file and hunk
        if current_hunk and current_file:
            current_file.hunks.append(current_hunk)
        if current_file:
            result.files.append(current_file)

        return result

    def _detect_language(self, filepath: str) -> Optional[str]:
        """Detect programming language from file extension."""
        for ext, lang in self.LANGUAGE_MAP.items():
            if filepath.endswith(ext):
                return lang
        return None

    def get_summary(self, parsed: ParsedDiff) -> str:
        """Generate a human-readable summary of the diff."""
        if not parsed.files:
            return "No files changed"

        lines = [
            f"Files changed: {parsed.file_count}",
            f"Lines added: {parsed.total_additions}",
            f"Lines removed: {parsed.total_deletions}",
        ]

        if parsed.languages:
            lines.append(f"Languages: {', '.join(parsed.languages)}")

        return "\n".join(lines)
