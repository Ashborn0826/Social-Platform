"""Entry point: `python -m app.media_processing` (starts the thumbnail worker)."""
import asyncio

from app.media_processing.worker import main

if __name__ == "__main__":
    asyncio.run(main())