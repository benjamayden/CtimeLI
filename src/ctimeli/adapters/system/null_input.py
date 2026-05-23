"""NullInputSource — InputSource that never yields lines or EOF.

Used by detached watch mode after the terminal is closed.
"""


class NullInputSource:
    """Non-blocking input with no source."""

    def poll_lines(self) -> list[str]:
        return []

    def closed(self) -> bool:
        return False

    def close(self) -> None:
        pass
