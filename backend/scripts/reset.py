"""make reset: wipe SQLite and Cognee memory (cognee.forget(everything=True))."""

import asyncio

import _path  # noqa: F401

from app.seed import reset_all


async def main() -> None:
    for note in await reset_all():
        print(note)


if __name__ == "__main__":
    asyncio.run(main())
