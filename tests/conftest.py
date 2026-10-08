"""Pytest bootstrap: put repo root on sys.path for `contracts.*` imports."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Unit suite stays hermetic now that ML libs are installed: no model
# downloads, no dense index, no chroma writes during tests. Real-model
# truth-checks run outside pytest with these unset.
os.environ.setdefault("EMBED_MODEL", "tfidf-local")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
