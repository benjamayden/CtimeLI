"""Scannable terminal copy — short lines, spaced sections, distinct tags.

One idea per line; blank lines between blocks; left-aligned tags so skimming
down the first column shows message type at a glance.
"""

from __future__ import annotations

from ctimeli import ports

_TAG_WIDTH = 6


def tagged(tag: str, message: str) -> str:
    """``TAG    message`` — tag column is fixed width."""
    return f"{tag:<{_TAG_WIDTH}}{message}"


def section(title: str) -> list[str]:
    """Blank line, uppercase heading, blank line."""
    return ["", title.upper(), ""]


def step(number: int, message: str) -> str:
    return f"  {number}. {message}"


def indent(message: str) -> str:
    return f"     {message}"


def prompt(message: str) -> str:
    return tagged("NEXT", message)


def ok(message: str) -> str:
    return tagged("OK", message)


def skip(message: str) -> str:
    return tagged("SKIP", message)


def warn(message: str) -> str:
    return tagged("!", message)


def emit_info(logger: ports.Logger, *lines: str) -> None:
    for line in lines:
        logger.info(line)


def emit_warn(logger: ports.Logger, *lines: str) -> None:
    for line in lines:
        logger.warn(line)
