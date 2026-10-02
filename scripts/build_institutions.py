from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.http_client import PoliteHttpClient
from config.settings import Settings
from institutions.master import OFFICIAL_DIRECTORY_URL, InstitutionMaster


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the official correctional institution master")
    parser.add_argument("--output", type=Path, default=Settings().institutions_path)
    args = parser.parse_args()
    settings = Settings()
    client = PoliteHttpClient(
        user_agent=settings.user_agent,
        timeout=settings.timeout_seconds,
        delay=settings.request_delay_seconds,
        retries=settings.retries,
    )
    response = client.get(OFFICIAL_DIRECTORY_URL)
    master = InstitutionMaster.from_official_html(response.content)
    master.save(args.output)
    print(f"Institution master written: {args.output}")
    print(f"Institutions: {len(master.institutions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
