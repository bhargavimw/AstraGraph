"""Launch the AstraGraph Streamlit app.

Usage:
    python scripts/run_app.py                 # opens http://localhost:8501
    python scripts/run_app.py --port 8600     # extra arguments go to Streamlit

Equivalent to:
    streamlit run app/demo.py

First-time setup (from the repository root):
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
    pip install -r requirements.txt

Live Camera mode needs camera permission in the browser. Browsers only allow
camera access on http://localhost or over HTTPS, so open the app on the same
computer that runs it (or put it behind HTTPS).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "demo.py"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if importlib.util.find_spec("streamlit") is None:
        print("Streamlit is not installed. Run: pip install -r requirements.txt",
              file=sys.stderr)
        return 1
    command = [sys.executable, "-m", "streamlit", "run", str(APP), *args]
    print("Starting AstraGraph:", " ".join(command[2:]))
    try:
        return subprocess.call(command, cwd=ROOT)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
