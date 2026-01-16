"""
Status Bar Widget

Displays application status including:
- Connection status
- R version
- Working directory
- Memory usage
- Key bindings help
"""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class ConnectionStatus(Static):
    """Shows connection status to rsession."""

    DEFAULT_CSS = """
    ConnectionStatus {
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, connected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.connected = connected

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        if self.connected:
            text = Text("[*] Connected", style="bold green")
        else:
            text = Text("[ ] Disconnected", style="dim red")
        self.update(text)

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        self._update_display()


class RVersionStatus(Static):
    """Shows R version."""

    DEFAULT_CSS = """
    RVersionStatus {
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, version: str = "R", **kwargs):
        super().__init__(**kwargs)
        self.version = version

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        text = Text(f"R {self.version}", style="cyan")
        self.update(text)

    def set_version(self, version: str) -> None:
        self.version = version
        self._update_display()


class WorkingDirStatus(Static):
    """Shows current working directory."""

    DEFAULT_CSS = """
    WorkingDirStatus {
        width: 1fr;
        padding: 0 1;
        text-align: left;
    }
    """

    def __init__(self, path: str = "~", **kwargs):
        super().__init__(**kwargs)
        self.path = path

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        # Truncate if too long
        display_path = self.path
        if len(display_path) > 40:
            display_path = "..." + display_path[-37:]
        text = Text(f"WD: {display_path}", style="dim")
        self.update(text)

    def set_path(self, path: str) -> None:
        self.path = path
        self._update_display()


class MemoryStatus(Static):
    """Shows memory usage."""

    DEFAULT_CSS = """
    MemoryStatus {
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, used_mb: float = 0, **kwargs):
        super().__init__(**kwargs)
        self.used_mb = used_mb

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        if self.used_mb < 1024:
            text = Text(f"Mem: {self.used_mb:.0f}MB", style="dim")
        else:
            text = Text(f"Mem: {self.used_mb / 1024:.1f}GB", style="dim yellow")
        self.update(text)

    def set_usage(self, used_mb: float) -> None:
        self.used_mb = used_mb
        self._update_display()


class KeyHints(Static):
    """Shows key binding hints."""

    DEFAULT_CSS = """
    KeyHints {
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        text = Text()
        hints = [
            ("F1", "Help"),
            ("F2", "Files"),
            ("F3", "Env"),
            ("^Q", "Quit"),
        ]
        for i, (key, action) in enumerate(hints):
            if i > 0:
                text.append(" | ", style="dim")
            text.append(key, style="bold yellow")
            text.append(f":{action}", style="dim")
        self.update(text)


class BusyIndicator(Static):
    """Shows busy/idle status."""

    DEFAULT_CSS = """
    BusyIndicator {
        width: auto;
        padding: 0 1;
    }
    """

    def __init__(self, busy: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.busy = busy

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        if self.busy:
            text = Text("[BUSY]", style="bold yellow blink")
        else:
            text = Text("[IDLE]", style="dim green")
        self.update(text)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self._update_display()


class StatusBarWidget(Horizontal):
    """
    Status bar widget showing application state.

    Features:
    - Connection status
    - R version info
    - Working directory
    - Memory usage
    - Key hints
    - Busy indicator
    """

    DEFAULT_CSS = """
    StatusBarWidget {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connection: Optional[ConnectionStatus] = None
        self._version: Optional[RVersionStatus] = None
        self._working_dir: Optional[WorkingDirStatus] = None
        self._memory: Optional[MemoryStatus] = None
        self._busy: Optional[BusyIndicator] = None

    def compose(self) -> ComposeResult:
        yield ConnectionStatus()
        yield RVersionStatus()
        yield BusyIndicator()
        yield WorkingDirStatus()
        yield MemoryStatus()
        yield KeyHints()

    def on_mount(self) -> None:
        self._connection = self.query_one(ConnectionStatus)
        self._version = self.query_one(RVersionStatus)
        self._working_dir = self.query_one(WorkingDirStatus)
        self._memory = self.query_one(MemoryStatus)
        self._busy = self.query_one(BusyIndicator)

    def set_connected(self, connected: bool) -> None:
        """Update connection status."""
        if self._connection:
            self._connection.set_connected(connected)

    def set_r_version(self, version: str) -> None:
        """Update R version display."""
        if self._version:
            self._version.set_version(version)

    def set_working_directory(self, path: str) -> None:
        """Update working directory display."""
        if self._working_dir:
            self._working_dir.set_path(path)

    def set_memory_usage(self, used_mb: float) -> None:
        """Update memory usage display."""
        if self._memory:
            self._memory.set_usage(used_mb)

    def set_busy(self, busy: bool) -> None:
        """Update busy indicator."""
        if self._busy:
            self._busy.set_busy(busy)
