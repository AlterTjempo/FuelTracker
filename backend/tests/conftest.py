import os
import sys
from pathlib import Path

# The app's settings require an API key at import time. Tests never call Tankerkönig, but CI has
# no config.env, so give the settings harmless placeholders (real values still win if present).
os.environ.setdefault("TANKERKONIG_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-test-secret-test-secret-123")

# Make the app modules importable (the app uses flat imports, e.g. `services.x`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
