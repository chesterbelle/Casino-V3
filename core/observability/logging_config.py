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
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_format: Output format ('json' for production, 'console' for development)
    """
    # Configure standard logging
    logging.basicConfig(
        format="%(asctime)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log", mode="w")],
        level=getattr(logging, log_level.upper()),
    )

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
