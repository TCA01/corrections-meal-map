from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit.sample_downloader import ParserSampleDownloader


def main() -> int:
    result = ParserSampleDownloader().run()
    print(f"SUCCESS: {result.success}")
    print(f"FAILED: {result.failed}")
    print(f"DEDUPLICATED: {result.deduplicated}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
