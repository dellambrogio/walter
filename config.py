"""Load local settings from config.local.json (git-ignored; see config.example.json)."""

import json
from pathlib import Path

_path = Path(__file__).with_name("config.local.json")
CONFIG = json.loads(_path.read_text(encoding="utf-8"))
TRAVEL = CONFIG["travel"]
