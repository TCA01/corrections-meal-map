from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from production.manifest import build_excel_manifest


if __name__ == "__main__":
    values = build_excel_manifest()
    print(json.dumps({"target_documents": len(values)}, ensure_ascii=False, indent=2))
