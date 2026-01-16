"""
RStudio TUI Main Application

The main Textual application that combines all widgets into a cohesive IDE interface.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static, Button, Input, Label

from rstudio_tui.client import RSessionClient, EventType
from rstudio_tui.widgets.console import ConsoleWidget
from rstudio_tui.widgets.editor import EditorWidget
from rstudio_tui.widgets.environment import EnvironmentWidget
from rstudio_tui.widgets.file_browser import FileBrowserWidget
from rstudio_tui.widgets.help_viewer import HelpViewerWidget
from rstudio_tui.widgets.history import HistoryWidget
from rstudio_tui.widgets.output import OutputWidget
from rstudio_tui.widgets.packages import PackagesWidget
from rstudio_tui.widgets.status_bar import StatusBarWidget


class QuitConfirmScreen(ModalScreen[bool]):
    """Modal screen for quit confirmation."""

    DEFAULT_CSS = """
    QuitConfirmScreen {
        align: center middle;
    }

    QuitConfirmScreen > Vertical {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    QuitConfirmScreen > Vertical > Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    QuitConfirmScreen > Vertical > Horizontal {
        width: 100%;
        height: auto;
        align: center middle;
    }

    QuitConfirmScreen Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Quit RStudio TUI?")
            yield Label("Unsaved changes will be lost.", classes="dim")
            with Horizontal():
                yield Button("Quit", variant="error", id="quit-btn")
                yield Button("Cancel", variant="primary", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)


class ConnectionScreen(ModalScreen[dict]):
    """Modal screen for connection settings."""

    DEFAULT_CSS = """
    ConnectionScreen {
        align: center middle;
    }

    ConnectionScreen > Vertical {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    ConnectionScreen Label {
        margin-top: 1;
    }

    ConnectionScreen Input {
        margin-bottom: 1;
    }

    ConnectionScreen > Vertical > Horizontal {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    ConnectionScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8787, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._port = port

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Connect to RStudio Session")
            yield Label("Host:")
            yield Input(value=self._host, id="host-input")
            yield Label("Port:")
            yield Input(value=str(self._port), id="port-input")
            with Horizontal():
                yield Button("Connect", variant="primary", id="connect-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect-btn":
            host_input = self.query_one("#host-input", Input)
            port_input = self.query_one("#port-input", Input)
            try:
                port = int(port_input.value)
            except ValueError:
                port = 8787
            self.dismiss({"host": host_input.value, "port": port})
        else:
            self.dismiss(None)


class RStudioTUI(App):
    """
    RStudio Terminal User Interface

    A complete TUI frontend for RStudio, providing:
    - R console with REPL
    - Source code editor
    - File browser
    - Environment viewer
    - Help system
    - History browser
    - Package manager
    - Output/plots viewer
    """

    TITLE = "RStudio TUI"
    SUB_TITLE = "Terminal User Interface for R"

    CSS = """
    /* Main layout */
    #main-container {
        layout: grid;
        grid-size: 3 2;
        grid-columns: 1fr 2fr 1fr;
        grid-rows: 1fr 1fr;
    }

    /* Left column - stacked vertically */
    #left-panel {
        column-span: 1;
        row-span: 2;
        layout: vertical;
    }

    #file-browser {
        height: 1fr;
    }

    #environment {
        height: 1fr;
    }

    /* Center column */
    #center-panel {
        column-span: 1;
        row-span: 2;
        layout: vertical;
    }

    #editor {
        height: 1fr;
    }

    #console {
        height: 1fr;
    }

    /* Right column */
    #right-panel {
        column-span: 1;
        row-span: 2;
        layout: vertical;
    }

    #help-viewer {
        height: 1fr;
    }

    #output {
        height: 1fr;
    }

    /* Focus styles */
    .focused {
        border: double $accent;
    }

    /* Hidden panels */
    .hidden {
        display: none;
    }

    /* Alternative views */
    #history-panel {
        display: none;
    }

    #packages-panel {
        display: none;
    }

    #history-panel.visible {
        display: block;
        height: 1fr;
    }

    #packages-panel.visible {
        display: block;
        height: 1fr;
    }
    """

    BINDINGS = [
        # Global bindings
        Binding("ctrl+q", "quit_app", "Quit", show=True, priority=True),
        Binding("ctrl+n", "new_file", "New File", show=False),
        Binding("ctrl+o", "open_file", "Open", show=False),
        Binding("ctrl+s", "save_file", "Save", show=False),

        # Panel focus bindings
        Binding("f1", "focus_console", "Console", show=True),
        Binding("f2", "focus_editor", "Editor", show=True),
        Binding("f3", "focus_files", "Files", show=True),
        Binding("f4", "focus_environment", "Environment", show=True),
        Binding("f5", "focus_help", "Help", show=True),
        Binding("f6", "toggle_history", "History", show=True),
        Binding("f7", "toggle_packages", "Packages", show=True),

        # Connection
        Binding("ctrl+shift+c", "connect", "Connect", show=False),
    ]

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8787,
        working_dir: Optional[Path] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._host = host
        self._port = port
        self._working_dir = working_dir or Path.cwd()
        self._client: Optional[RSessionClient] = None
        self._connected: bool = False

        # Widget references
        self._console: Optional[ConsoleWidget] = None
        self._editor: Optional[EditorWidget] = None
        self._file_browser: Optional[FileBrowserWidget] = None
        self._environment: Optional[EnvironmentWidget] = None
        self._help_viewer: Optional[HelpViewerWidget] = None
        self._history: Optional[HistoryWidget] = None
        self._packages: Optional[PackagesWidget] = None
        self._output: Optional[OutputWidget] = None
        self._status_bar: Optional[StatusBarWidget] = None

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="main-container"):
            # Left panel - Files and Environment
            with Vertical(id="left-panel"):
                yield FileBrowserWidget(
                    client=self._client,
                    initial_path=self._working_dir,
                    id="file-browser",
                )
                yield EnvironmentWidget(client=self._client, id="environment")
                yield HistoryWidget(
                    client=self._client,
                    on_command_selected=self._run_history_command,
                    id="history-panel",
                )
                yield PackagesWidget(client=self._client, id="packages-panel")

            # Center panel - Editor and Console
            with Vertical(id="center-panel"):
                yield EditorWidget(client=self._client, id="editor")
                yield ConsoleWidget(client=self._client, id="console")

            # Right panel - Help and Output
            with Vertical(id="right-panel"):
                yield HelpViewerWidget(client=self._client, id="help-viewer")
                yield OutputWidget(id="output")

        yield StatusBarWidget()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the application after mounting."""
        # Get widget references
        self._console = self.query_one("#console", ConsoleWidget)
        self._editor = self.query_one("#editor", EditorWidget)
        self._file_browser = self.query_one("#file-browser", FileBrowserWidget)
        self._environment = self.query_one("#environment", EnvironmentWidget)
        self._help_viewer = self.query_one("#help-viewer", HelpViewerWidget)
        self._history = self.query_one("#history-panel", HistoryWidget)
        self._packages = self.query_one("#packages-panel", PackagesWidget)
        self._output = self.query_one("#output", OutputWidget)
        self._status_bar = self.query_one(StatusBarWidget)

        # Set initial status
        self._status_bar.set_working_directory(str(self._working_dir))
        self._status_bar.set_connected(False)

        # Focus console initially
        self._console.focus_input()

        # Try to connect to rsession
        self.call_later(self._auto_connect)

    async def _auto_connect(self) -> None:
        """Attempt automatic connection to rsession."""
        # Check for environment variables that indicate rsession connection info
        port = os.environ.get("RS_SESSION_PORT")
        if port:
            try:
                self._port = int(port)
            except ValueError:
                pass

        # Try to connect
        await self._do_connect(self._host, self._port)

    async def _do_connect(self, host: str, port: int) -> bool:
        """Connect to rsession."""
        self._client = RSessionClient(host=host, port=port)

        try:
            if await self._client.connect():
                self._connected = True
                self._setup_event_handlers()
                self._client.start_event_polling()
                self._update_widget_clients()
                self._status_bar.set_connected(True)
                self.notify("Connected to R session")

                # Get session info
                response = await self._client.get_session_info()
                if response.success:
                    info = response.result or {}
                    version = info.get("r_version", "4.x")
                    self._status_bar.set_r_version(version)

                return True
            else:
                self.notify("Could not connect to R session", severity="warning")
                return False
        except Exception as e:
            self.notify(f"Connection failed: {e}", severity="error")
            return False

    def _setup_event_handlers(self) -> None:
        """Set up handlers for rsession events."""
        if not self._client:
            return

        # Console output
        self._client.on_event(EventType.CONSOLE_WRITE_OUTPUT, self._on_console_output)
        self._client.on_event(EventType.CONSOLE_WRITE_ERROR, self._on_console_error)
        self._client.on_event(EventType.CONSOLE_PROMPT, self._on_console_prompt)

        # State changes
        self._client.on_event(EventType.BUSY, self._on_busy)
        self._client.on_event(EventType.WORKING_DIR_CHANGED, self._on_working_dir_changed)
        self._client.on_event(EventType.ENVIRONMENT_REFRESH, self._on_environment_refresh)
        self._client.on_event(EventType.PACKAGE_STATE_CHANGED, self._on_package_state_changed)
        self._client.on_event(EventType.PLOTS_STATE_CHANGED, self._on_plots_changed)
        self._client.on_event(EventType.MEMORY_USAGE_CHANGED, self._on_memory_changed)
        self._client.on_event(EventType.HISTORY_ENTRIES_ADDED, self._on_history_added)

    def _update_widget_clients(self) -> None:
        """Update all widgets with the client reference."""
        if self._console:
            self._console.client = self._client
        if self._editor:
            self._editor.client = self._client
        if self._file_browser:
            self._file_browser.client = self._client
        if self._environment:
            self._environment.client = self._client
        if self._help_viewer:
            self._help_viewer.client = self._client
        if self._history:
            self._history.client = self._client
        if self._packages:
            self._packages.client = self._client

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def _on_console_output(self, event) -> None:
        """Handle console output event."""
        if self._console and event.data:
            self._console.write_output(event.data)

    def _on_console_error(self, event) -> None:
        """Handle console error event."""
        if self._console and event.data:
            self._console.write_error(event.data)

    def _on_console_prompt(self, event) -> None:
        """Handle console prompt event."""
        if self._console and event.data:
            prompt = event.data.get("prompt", "> ")
            self._console.set_prompt(prompt)
            self._console.set_busy(False)
        if self._status_bar:
            self._status_bar.set_busy(False)

    def _on_busy(self, event) -> None:
        """Handle busy state change."""
        busy = event.data if isinstance(event.data, bool) else event.data.get("busy", False)
        if self._console:
            self._console.set_busy(busy)
        if self._status_bar:
            self._status_bar.set_busy(busy)

    def _on_working_dir_changed(self, event) -> None:
        """Handle working directory change."""
        if event.data:
            path = event.data.get("path", event.data)
            self._working_dir = Path(path)
            if self._status_bar:
                self._status_bar.set_working_directory(str(path))
            if self._file_browser:
                asyncio.create_task(self._file_browser.set_path(self._working_dir))

    def _on_environment_refresh(self, event) -> None:
        """Handle environment refresh event."""
        if self._environment:
            asyncio.create_task(self._environment.refresh())

    def _on_package_state_changed(self, event) -> None:
        """Handle package state change."""
        if self._packages:
            asyncio.create_task(self._packages.refresh())

    def _on_plots_changed(self, event) -> None:
        """Handle plot state change."""
        if self._output and event.data:
            plot_file = event.data.get("filename")
            if plot_file:
                self._output.add_plot(plot_file)

    def _on_memory_changed(self, event) -> None:
        """Handle memory usage change."""
        if self._status_bar and event.data:
            used = event.data.get("used", 0)
            # Convert to MB
            used_mb = used / (1024 * 1024)
            self._status_bar.set_memory_usage(used_mb)

    def _on_history_added(self, event) -> None:
        """Handle history entries added."""
        if self._history:
            asyncio.create_task(self._history.refresh())

    # -------------------------------------------------------------------------
    # File Browser Events
    # -------------------------------------------------------------------------

    def on_file_browser_widget_file_selected(self, event: FileBrowserWidget.FileSelected) -> None:
        """Handle file selection from browser."""
        asyncio.create_task(self._open_file_in_editor(event.path))

    async def _open_file_in_editor(self, path: Path) -> None:
        """Open a file in the editor."""
        if self._editor:
            await self._editor.open_file(path)
            self._editor.focus_editor()

    # -------------------------------------------------------------------------
    # History Events
    # -------------------------------------------------------------------------

    def _run_history_command(self, command: str) -> None:
        """Run a command from history."""
        if self._console:
            self._console._handle_submit(command)
            self._console.focus_input()

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    async def action_quit_app(self) -> None:
        """Quit the application with confirmation."""
        # Check for unsaved changes
        if self._editor and self._editor.is_modified:
            result = await self.push_screen_wait(QuitConfirmScreen())
            if not result:
                return

        # Disconnect from rsession
        if self._client:
            await self._client.disconnect()

        self.exit()

    async def action_connect(self) -> None:
        """Show connection dialog."""
        result = await self.push_screen_wait(
            ConnectionScreen(host=self._host, port=self._port)
        )
        if result:
            await self._do_connect(result["host"], result["port"])

    async def action_new_file(self) -> None:
        """Create a new file in the editor."""
        if self._editor:
            self._editor.new_file()
            self._editor.focus_editor()

    async def action_open_file(self) -> None:
        """Focus file browser to open a file."""
        if self._file_browser:
            self._file_browser.focus()

    async def action_save_file(self) -> None:
        """Save the current file."""
        if self._editor:
            self._editor._handle_save()

    def action_focus_console(self) -> None:
        """Focus the console."""
        if self._console:
            self._console.focus_input()

    def action_focus_editor(self) -> None:
        """Focus the editor."""
        if self._editor:
            self._editor.focus_editor()

    def action_focus_files(self) -> None:
        """Focus the file browser."""
        if self._file_browser:
            self._file_browser.focus()

    def action_focus_environment(self) -> None:
        """Focus the environment viewer."""
        if self._environment:
            self._environment.focus()

    def action_focus_help(self) -> None:
        """Focus the help viewer."""
        if self._help_viewer:
            self._help_viewer.focus()

    def action_toggle_history(self) -> None:
        """Toggle history panel visibility."""
        history = self.query_one("#history-panel")
        env = self.query_one("#environment")

        if "visible" in history.classes:
            history.remove_class("visible")
            env.remove_class("hidden")
        else:
            history.add_class("visible")
            env.add_class("hidden")
            history.focus()

    def action_toggle_packages(self) -> None:
        """Toggle packages panel visibility."""
        packages = self.query_one("#packages-panel")
        help_viewer = self.query_one("#help-viewer")

        if "visible" in packages.classes:
            packages.remove_class("visible")
            help_viewer.remove_class("hidden")
        else:
            packages.add_class("visible")
            help_viewer.add_class("hidden")
            packages.focus()


def run_tui(
    host: str = "127.0.0.1",
    port: int = 8787,
    working_dir: Optional[Path] = None,
) -> None:
    """
    Run the RStudio TUI application.

    Args:
        host: rsession host address
        port: rsession port
        working_dir: Initial working directory
    """
    app = RStudioTUI(host=host, port=port, working_dir=working_dir)
    app.run()
