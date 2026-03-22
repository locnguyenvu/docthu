"""
Entry point: python -m docthu  or  docthu  (after pip install)

Launches the Streamlit template builder app.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    app = Path(__file__).parent / "app.py"
    sys.exit(subprocess.call(["streamlit", "run", str(app)] + sys.argv[1:]))


if __name__ == "__main__":
    main()
