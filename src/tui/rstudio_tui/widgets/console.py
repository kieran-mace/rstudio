"""
Console Widget - R REPL Interface

Provides an interactive R console with:
- Command input with history
- Syntax highlighting
- Output display
- Code completion
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Callable, Optional

from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Static

if TYPE_CHECKING:
    from rstudio_tui.client import RSessionClient


class ConsoleOutput(Static):
    """Widget for displaying console output."""

    DEFAULT_CSS = """
    ConsoleOutput {
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, text: str = "", output_type: str = "output", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.output_type = output_type

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        if self.output_type == "input":
            # Format input with > prefix
            content = Text()
            content.append("> ", style="bold blue")
            content.append(self.text, style="cyan")
            self.update(content)
        elif self.output_type == "error":
            content = Text(self.text, style="bold red")
            self.update(content)
        elif self.output_type == "warning":
            content = Text(self.text, style="yellow")
            self.update(content)
        elif self.output_type == "prompt":
            content = Text(self.text, style="bold green")
            self.update(content)
        else:
            # Regular output - try syntax highlighting for R
            self.update(self.text)


class ConsoleHistory:
    """Manages console command history."""

    def __init__(self, max_size: int = 1000):
        self.history: deque[str] = deque(maxlen=max_size)
        self._position: int = -1
        self._current_input: str = ""

    def add(self, command: str) -> None:
        """Add a command to history."""
        if command.strip():
            # Don't add duplicates of the last command
            if not self.history or self.history[-1] != command:
                self.history.append(command)
        self._position = -1
        self._current_input = ""

    def start_navigation(self, current_input: str) -> None:
        """Start navigating history, saving current input."""
        if self._position == -1:
            self._current_input = current_input

    def previous(self) -> Optional[str]:
        """Get the previous command in history."""
        if not self.history:
            return None

        if self._position == -1:
            self._position = len(self.history) - 1
        elif self._position > 0:
            self._position -= 1

        return self.history[self._position]

    def next(self) -> Optional[str]:
        """Get the next command in history."""
        if self._position == -1:
            return None

        if self._position < len(self.history) - 1:
            self._position += 1
            return self.history[self._position]
        else:
            self._position = -1
            return self._current_input

    def reset(self) -> None:
        """Reset history navigation."""
        self._position = -1
        self._current_input = ""


class ConsoleInput(Input):
    """Input widget for console commands with history navigation."""

    BINDINGS = [
        Binding("up", "history_prev", "Previous command", show=False),
        Binding("down", "history_next", "Next command", show=False),
        Binding("ctrl+c", "interrupt", "Interrupt", show=False),
        Binding("tab", "complete", "Complete", show=False),
    ]

    DEFAULT_CSS = """
    ConsoleInput {
        dock: bottom;
        height: 1;
        border: none;
        background: $surface;
    }

    ConsoleInput:focus {
        border: none;
    }

    ConsoleInput > .input--placeholder {
        color: $text-muted;
    }
    """

    def __init__(
        self,
        history: ConsoleHistory,
        on_submit: Optional[Callable[[str], None]] = None,
        on_interrupt: Optional[Callable[[], None]] = None,
        on_complete: Optional[Callable[[str, int], None]] = None,
        **kwargs,
    ):
        super().__init__(placeholder="> Enter R command...", **kwargs)
        self.history = history
        self._on_submit = on_submit
        self._on_interrupt = on_interrupt
        self._on_complete = on_complete

    async def action_history_prev(self) -> None:
        """Navigate to previous command in history."""
        self.history.start_navigation(self.value)
        prev_cmd = self.history.previous()
        if prev_cmd is not None:
            self.value = prev_cmd
            self.cursor_position = len(self.value)

    async def action_history_next(self) -> None:
        """Navigate to next command in history."""
        next_cmd = self.history.next()
        if next_cmd is not None:
            self.value = next_cmd
            self.cursor_position = len(self.value)

    async def action_interrupt(self) -> None:
        """Send interrupt signal."""
        if self._on_interrupt:
            self._on_interrupt()

    async def action_complete(self) -> None:
        """Trigger code completion."""
        if self._on_complete:
            self._on_complete(self.value, self.cursor_position)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission."""
        command = self.value.strip()
        if command:
            self.history.add(command)
            if self._on_submit:
                self._on_submit(command)
        self.value = ""
        self.history.reset()


class ConsoleWidget(Vertical):
    """
    Main console widget providing R REPL interaction.

    Features:
    - Command history with up/down arrow navigation
    - Syntax-highlighted output
    - Code completion
    - Interrupt support (Ctrl+C)
    """

    DEFAULT_CSS = """
    ConsoleWidget {
        height: 100%;
        border: solid $primary;
    }

    ConsoleWidget > .console-title {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }

    ConsoleWidget > VerticalScroll {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear", "Clear console"),
    ]

    def __init__(
        self,
        client: Optional[RSessionClient] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self.history = ConsoleHistory()
        self._output_container: Optional[VerticalScroll] = None
        self._input: Optional[ConsoleInput] = None
        self._prompt: str = "> "
        self._busy: bool = False

    def compose(self) -> ComposeResult:
        yield Static("Console", classes="console-title")
        with VerticalScroll() as scroll:
            self._output_container = scroll
            yield ConsoleOutput("R version 4.x.x -- \"TUI Edition\"", output_type="output")
            yield ConsoleOutput("Type 'help()' for help.", output_type="output")
        yield ConsoleInput(
            history=self.history,
            on_submit=self._handle_submit,
            on_interrupt=self._handle_interrupt,
            on_complete=self._handle_complete,
        )

    def on_mount(self) -> None:
        self._input = self.query_one(ConsoleInput)
        self._output_container = self.query_one(VerticalScroll)

    def _handle_submit(self, command: str) -> None:
        """Handle command submission."""
        # Display the input
        self._append_output(command, "input")

        # Send to rsession if connected
        if self.client:
            asyncio.create_task(self._execute_command(command))
        else:
            # Demo mode - just echo
            self._append_output(f"[Not connected] Would execute: {command}", "warning")

    async def _execute_command(self, command: str) -> None:
        """Execute a command via rsession."""
        self._busy = True
        self._update_prompt()

        try:
            response = await self.client.console_input(command)
            if not response.success:
                self._append_output(f"Error: {response.error_message}", "error")
        except Exception as e:
            self._append_output(f"Error: {e}", "error")
        finally:
            self._busy = False
            self._update_prompt()

    def _handle_interrupt(self) -> None:
        """Handle interrupt request."""
        if self.client:
            asyncio.create_task(self._do_interrupt())
        else:
            self._append_output("^C", "warning")

    async def _do_interrupt(self) -> None:
        """Send interrupt to rsession."""
        try:
            await self.client.interrupt()
            self._append_output("^C", "warning")
        except Exception as e:
            self._append_output(f"Interrupt error: {e}", "error")

    def _handle_complete(self, text: str, cursor_pos: int) -> None:
        """Handle code completion request."""
        if self.client:
            asyncio.create_task(self._do_complete(text, cursor_pos))

    async def _do_complete(self, text: str, cursor_pos: int) -> None:
        """Get completions from rsession."""
        try:
            response = await self.client.get_completions(text, cursor_pos)
            if response.success and response.result:
                completions = response.result.get("completions", [])
                if completions:
                    # For now, just show completions
                    comp_text = ", ".join(c.get("value", "") for c in completions[:10])
                    self._append_output(f"Completions: {comp_text}", "output")
        except Exception as e:
            pass  # Silently fail on completion errors

    def _append_output(self, text: str, output_type: str = "output") -> None:
        """Append output to the console."""
        if self._output_container:
            output = ConsoleOutput(text, output_type=output_type)
            self._output_container.mount(output)
            self._output_container.scroll_end()

    def _update_prompt(self) -> None:
        """Update the input prompt based on state."""
        if self._input:
            if self._busy:
                self._input.placeholder = "Running..."
            else:
                self._input.placeholder = f"{self._prompt} Enter R command..."

    def write_output(self, text: str) -> None:
        """Write output from rsession."""
        self._append_output(text, "output")

    def write_error(self, text: str) -> None:
        """Write error output from rsession."""
        self._append_output(text, "error")

    def set_prompt(self, prompt: str) -> None:
        """Set the console prompt."""
        self._prompt = prompt
        self._update_prompt()

    def set_busy(self, busy: bool) -> None:
        """Set the busy state."""
        self._busy = busy
        self._update_prompt()

    async def action_clear(self) -> None:
        """Clear the console output."""
        if self._output_container:
            await self._output_container.remove_children()
            self._append_output("Console cleared.", "output")

    def focus_input(self) -> None:
        """Focus the input field."""
        if self._input:
            self._input.focus()
