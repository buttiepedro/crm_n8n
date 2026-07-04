"""Logging estructurado con structlog.

JSON a stdout en staging/producción (formato compatible con Cloud Logging:
campos `severity`, `message`, `time`); consola legible en desarrollo.
El trace_id se propaga vía contextvars (ver middleware en main.py).
"""

import logging

import structlog

_SEVERITY = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "error": "ERROR",
    "critical": "CRITICAL",
}

# Claves que jamás deben llegar a un log técnico
_REDACT_KEYS = {"password", "token", "access_token", "api_key", "secret", "authorization", "body"}


def _add_severity(_logger, method_name: str, event_dict: dict) -> dict:
    event_dict["severity"] = _SEVERITY.get(method_name, method_name.upper())
    return event_dict


def _redact_sensitive(_logger, _method_name: str, event_dict: dict) -> dict:
    for key in list(event_dict):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _add_severity,
        _redact_sensitive,
        structlog.processors.TimeStamper(fmt="iso", key="time"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors += [
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_values) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(**initial_values)


def current_trace_id() -> str | None:
    return structlog.contextvars.get_contextvars().get("trace_id")
