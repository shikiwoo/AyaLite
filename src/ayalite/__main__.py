import asyncio
import logging

from ayalite import bot


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
