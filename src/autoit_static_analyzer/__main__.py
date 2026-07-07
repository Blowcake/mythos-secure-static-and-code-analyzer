"""@file __main__.py
@brief Package entry point for invoking the AutoIt static analyzer with python -m.
@details Part of AutoIt_Static_Analyzer. This header is intentionally concise so Doxygen output and future code reviews expose the module boundary before implementation details.
@author Harald Frank
@copyright Copyright (c) 2026 Harald Frank. All rights reserved.
"""
from .autoit_windows_x64_scoping_analyzer import main


if __name__ == "__main__":
    main()
