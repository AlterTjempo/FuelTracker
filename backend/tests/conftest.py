import sys
from pathlib import Path

# Make the app modules importable (the app uses flat imports, e.g. `services.x`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
