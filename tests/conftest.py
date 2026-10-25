import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TAGOUT_OFFLINE", "1")  # tests never call the API; demo texts come from seeds/llm_cache
