from __future__ import annotations

import logging

from workers.collectors.rss_collector import run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

if __name__ == "__main__":
    summary = run()
    print(summary)
