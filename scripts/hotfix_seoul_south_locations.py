"""Apply only the Phase 4B.1 Seoul South user-provided address geocodes."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from institutions.seoul_south_hotfix import apply_hotfix

if __name__ == '__main__':
    print(json.dumps(apply_hotfix(), ensure_ascii=True, indent=2))
