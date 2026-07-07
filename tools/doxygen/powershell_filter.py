"""@file powershell_filter.py
@brief Doxygen filter for projecting PowerShell scripts into C++-like declarations.
@details The filter preserves comment-based help as Doxygen comments and emits
pseudo declarations for named PowerShell functions when present.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


FUNCTION_RE = re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_-]*)\b", re.IGNORECASE)


def _read_input() -> str:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def convert_powershell(source: str) -> str:
    """Return a Doxygen-readable projection of a PowerShell source file."""
    out = ["namespace autoit_static_analyzer_powershell {", ""]
    in_block_comment = False

    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("<#"):
            in_block_comment = True
            tail = stripped[2:].strip()
            out.append("/// " + tail if tail else "///")
            continue
        if stripped.endswith("#>"):
            head = stripped[:-2].strip()
            if head:
                out.append("/// " + head)
            out.append("///")
            in_block_comment = False
            continue
        if in_block_comment:
            out.append("/// " + stripped)
            continue
        if stripped.startswith("#"):
            out.append("/// " + stripped[1:].lstrip())
            continue

        match = FUNCTION_RE.match(line)
        if match:
            safe_name = match.group(1).replace("-", "_")
            out.append(f"void {safe_name}();")
            out.append("")

    out.extend(["}", ""])
    return "\n".join(out)


def main() -> None:
    sys.stdout.write(convert_powershell(_read_input()))


if __name__ == "__main__":
    main()
