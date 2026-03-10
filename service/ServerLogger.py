import logging

logger = logging.getLogger("uvicorn.error")

class ServerLogger:

    boot = "🥾"
    spark = "⚡"
    pallette = "🎨"
    fire = "🔥"
    bug = "🐛"
    hotfix = "🚑"
    feature = "✨"
    doc = "📝"
    deploy = "🚀"
    WIP = "🚧"
    drunk = "🍻"
    party = "🎉"
    python = "🐍"
    verbose = "🔊"
    confusion = "🌀"
    accurate = "📘"
    drama = "🎭"
    docs = "📚"

    def info(self, message: str, **kwargs):
        logger.info(message, **kwargs)

    def warn(self, message: str, **kwargs):
        logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs):
        logger.critical(message, **kwargs)

    def deb(self, message: str, **kwargs):
        logger.debug(message, **kwargs)
