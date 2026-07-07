"""@file autoit_filter.py
@brief Doxygen filter for projecting AutoIt source into C++-like declarations.
@details Doxygen does not parse AutoIt natively. This filter keeps source files
documented in idiomatic AutoIt comments while exposing file and function headers
to Doxygen as `///` comments and pseudo declarations.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


FUNC_RE = re.compile(r"^\s*Func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$", re.IGNORECASE)


def _read_input() -> str:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _split_params(raw: str) -> list[str]:
    params: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    for ch in raw:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            current.append(ch)
        elif ch in "([{":
            depth += 1
            current.append(ch)
        elif ch in ")]}":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            params.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        params.append(tail)
    return params


def _normalize_param(param: str) -> str | None:
    param = re.sub(r"\b(ByRef|Const)\b", "", param, flags=re.IGNORECASE).strip()
    param = param.split("=", 1)[0].strip()
    match = re.search(r"\$([A-Za-z_][A-Za-z0-9_]*)", param)
    if not match:
        return None
    return "auto " + match.group(1)


def convert_autoit(source: str) -> str:
    """Return a Doxygen-readable projection of an AutoIt source file."""
    out = ["namespace autoit_static_analyzer_autoit {", ""]
    in_block_comment = False

    for line in source.splitlines():
        stripped = line.strip()
        if re.match(r"^#(cs|comments-start)\b", stripped, re.IGNORECASE):
            in_block_comment = True
            out.append("///")
            continue
        if re.match(r"^#(ce|comments-end)\b", stripped, re.IGNORECASE):
            in_block_comment = False
            out.append("///")
            continue

        if in_block_comment:
            out.append("/// " + stripped)
            continue

        if stripped.startswith(";"):
            comment = stripped[1:].lstrip()
            comment = re.sub(r'#(\w+)', r'\#\1', comment)
            out.append("/// " + comment)
            continue

        match = FUNC_RE.match(line)
        if match:
            params = [_normalize_param(param) for param in _split_params(match.group(2).strip())]
            rendered = ", ".join(param for param in params if param)
            out.append(f"void {match.group(1)}({rendered});")
            out.append("")

    out.extend(["}", ""])
    return "\n".join(out)


def main() -> None:
    sys.stdout.write(convert_autoit(_read_input()))


if __name__ == "__main__":
    main()
