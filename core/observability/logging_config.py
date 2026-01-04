"""
Structured Logging Configuration for Casino V3.

Provides JSON logging for production and pretty console logging for development.

Author: Casino V3 Team
Version: 2.0.0
"""

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO", log_format: str = "console"):
    """
    Configure structured logging.

    Args:
        log_level: Logging level for Console (DEBUG, INFO, WARNING, ERROR)
        log_format: Output format ('json' for production, 'console' for development)
    """
    # Create Root Logger
    root_logger = logging.getLogger()
    # Force DEBUG on root to allow handlers to decide their own thresholds
    root_logger.setLevel(logging.DEBUG)

    # Clear existing handlers to prevent duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 1. Console Handler (Human-Friendly)
    # This handler respects the 'log_level' argument (usually INFO)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # Use simple format for console
    console_formatter = logging.Formatter(
        "%(asctime)s | %(name)-15s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)

    # 2. File Handler (human.log - Sync with Console)
    # This handler mirrors the console for remote monitoring (tail -f)
    human_handler = logging.FileHandler("human.log", mode="w")
    human_handler.setLevel(getattr(logging, log_level.upper()))
    human_handler.setFormatter(console_formatter)

    # 3. File Handler (bot.log - AI Blackbox / Debug)
    # This handler is ALWAYS DEBUG to ensure no info is lost for AI debugging
    file_handler = logging.FileHandler("bot.log", mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] [%(funcName)s:%(lineno)d] %(message)s")
    file_handler.setFormatter(file_formatter)

    # Add all handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(human_handler)
    root_logger.addHandler(file_handler)

    # Suppress talkative third-party libraries globally in console (but keep in file)
    # We do this by setting their specific logger levels higher than DEBUG
    # Note: This affects BOTH handlers if we just setLevel, so we use a Filter instead
    # OR we just accept that file will have them if root is DEBUG.

    logging.getLogger("websockets").setLevel(logging.INFO)  # Suppress ultra-raw frames even in bot.log if too much
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.INFO)

    # Shared processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if log_format == "json":
        # Production: JSON output
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Pretty console output
        processors = shared_processors + [
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None):
    """
    Get a structured logger.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


# Convenience function for adding context
def bind_context(**kwargs):
    """
    Bind context variables to all subsequent log messages.

    Example:
        bind_context(user_id="123", session_id="abc")
        logger.info("user_action", action="login")
        # Output includes user_id and session_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys):
    """
    Remove context variables.

    Example:
        unbind_context("user_id", "session_id")
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context():
    """Clear all context variables."""
    structlog.contextvars.clear_contextvars()
