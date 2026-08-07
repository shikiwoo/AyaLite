import asyncio
import logging


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[{asctime}] [{levelname:<8}] {name}: {message}",
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # both libraries are extremely chatty below WARNING
    logging.getLogger("twitch").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)

    # imported here rather than at module scope so `import ayalite.<submodule>`
    # doesn't drag in discord/dotenv as a side effect
    from ayalite.bot import run

    try:
        asyncio.run(run())
    # KeyboardInterrupt is ctrl-c; CancelledError is what asyncio.run re-raises
    # after a signal handler cancelled the main task. cleanup has already run by
    # the time either lands here.
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.getLogger(__name__).info("shutting down")
