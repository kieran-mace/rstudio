"""
Help Viewer Widget

Displays R help documentation with:
- Help topic rendering
- Search functionality
- Navigation history
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, List, Optional

from rich.markdown import Markdown
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Static

if TYPE_CHECKING:
    from rstudio_tui.client import RSessionClient


class HelpHeader(Static):
    """Header showing current help topic."""

    DEFAULT_CSS = """
    HelpHeader {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, topic: str = "Help", **kwargs):
        super().__init__(**kwargs)
        self.topic = topic

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        self.update(f"Help: {self.topic}")

    def set_topic(self, topic: str) -> None:
        self.topic = topic
        self._update_display()


class HelpSearchInput(Input):
    """Search input for help topics."""

    DEFAULT_CSS = """
    HelpSearchInput {
        dock: top;
        height: 1;
        margin: 0;
        border: none;
        background: $surface;
    }
    """

    def __init__(self, on_search: Optional[callable] = None, **kwargs):
        super().__init__(placeholder="Search help...", **kwargs)
        self._on_search = on_search

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission."""
        query = self.value.strip()
        if query and self._on_search:
            self._on_search(query)
        self.value = ""


class HelpContent(Static):
    """Widget for displaying help content."""

    DEFAULT_CSS = """
    HelpContent {
        height: auto;
        padding: 1;
    }
    """

    def __init__(self, content: str = "", **kwargs):
        super().__init__(**kwargs)
        self._content = content

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        """Render the help content."""
        if self._content:
            # Convert R help format to something displayable
            # R help is typically in Rd format, but we'll handle HTML or plain text
            formatted = self._format_help(self._content)
            self.update(formatted)
        else:
            self.update("No help content loaded.\n\nTry searching for a topic above.")

    def _format_help(self, content: str) -> Text:
        """Format R help content for terminal display."""
        text = Text()

        # Simple parsing of common R help sections
        lines = content.split("\n")
        in_section = None

        for line in lines:
            # Section headers
            if line.startswith("_") and line.endswith("_"):
                section_name = line.strip("_")
                text.append(f"\n{section_name}\n", style="bold underline cyan")
                text.append("=" * len(section_name) + "\n", style="dim")
                in_section = section_name
            # Code blocks
            elif line.startswith("     "):
                text.append(line + "\n", style="green")
            # Arguments
            elif line.startswith("  ") and ":" in line[:20]:
                parts = line.split(":", 1)
                text.append(parts[0] + ":", style="bold yellow")
                if len(parts) > 1:
                    text.append(parts[1] + "\n")
                else:
                    text.append("\n")
            # Regular text
            else:
                text.append(line + "\n")

        return text

    def set_content(self, content: str) -> None:
        """Set the help content."""
        self._content = content
        self._render_content()


class HelpViewerWidget(Vertical):
    """
    Help viewer widget for R documentation.

    Features:
    - Display help for R functions and packages
    - Search help topics
    - Navigate help history
    - Cross-reference links
    """

    DEFAULT_CSS = """
    HelpViewerWidget {
        height: 100%;
        border: solid $secondary;
    }

    HelpViewerWidget > VerticalScroll {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    BINDINGS = [
        Binding("slash", "focus_search", "Search", show=True),
        Binding("left", "back", "Back", show=True),
        Binding("right", "forward", "Forward", show=True),
        Binding("h", "home", "Home", show=True),
    ]

    def __init__(
        self,
        client: Optional[RSessionClient] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self._header: Optional[HelpHeader] = None
        self._search: Optional[HelpSearchInput] = None
        self._content: Optional[HelpContent] = None
        self._history: List[str] = []
        self._history_pos: int = -1

    def compose(self) -> ComposeResult:
        yield HelpHeader()
        yield HelpSearchInput(on_search=self._handle_search)
        with VerticalScroll():
            yield HelpContent()

    def on_mount(self) -> None:
        self._header = self.query_one(HelpHeader)
        self._search = self.query_one(HelpSearchInput)
        self._content = self.query_one(HelpContent)

        # Show welcome message
        self._show_home()

    def _show_home(self) -> None:
        """Show the help home page."""
        home_content = """
_R Help System_

Welcome to the RStudio TUI Help Viewer.

_Quick Start_

Type a function or topic name in the search box above, or use these shortcuts:

  ?function_name  - Get help on a function
  ??search_term   - Search help topics
  help(package)   - Package documentation

_Common Help Topics_

  help            - The help system
  library         - Load packages
  install.packages - Install packages
  data.frame      - Data frames
  read.csv        - Read CSV files
  ggplot2         - Grammar of graphics
  dplyr           - Data manipulation

_Keyboard Shortcuts_

  /               - Focus search
  Left Arrow      - Go back
  Right Arrow     - Go forward
  h               - Return home

_Getting Started with R_

If you're new to R, try:
  help.start()    - Open HTML help browser
  demo()          - See R demos
  example(mean)   - Run function examples
"""
        if self._content:
            self._content.set_content(home_content)
        if self._header:
            self._header.set_topic("Home")

    def _handle_search(self, query: str) -> None:
        """Handle help search."""
        asyncio.create_task(self._do_search(query))

    async def _do_search(self, query: str) -> None:
        """Perform help search."""
        if self._header:
            self._header.set_topic(query)

        # Add to history
        self._history.append(query)
        self._history_pos = len(self._history) - 1

        if self.client:
            try:
                # Check if it's a direct help request (starts with ?)
                if query.startswith("??"):
                    # Search help
                    search_term = query[2:].strip()
                    response = await self.client.search_help(search_term)
                    if response.success:
                        self._show_search_results(search_term, response.result)
                    else:
                        self._show_error(f"Search failed: {response.error_message}")
                elif query.startswith("?"):
                    # Direct help lookup
                    topic = query[1:].strip()
                    await self._load_help(topic)
                else:
                    # Try direct help first
                    await self._load_help(query)
            except Exception as e:
                self._show_error(f"Help error: {e}")
        else:
            # Demo mode - show placeholder
            self._show_demo_help(query)

    async def _load_help(self, topic: str, package: Optional[str] = None) -> None:
        """Load help for a specific topic."""
        if not self.client:
            self._show_demo_help(topic)
            return

        try:
            response = await self.client.get_help(topic, package)
            if response.success:
                content = response.result.get("content", "")
                if self._content:
                    self._content.set_content(content)
            else:
                self._show_error(f"No help found for '{topic}'")
        except Exception as e:
            self._show_error(f"Failed to load help: {e}")

    def _show_search_results(self, query: str, results: List) -> None:
        """Show search results."""
        if not results:
            self._show_error(f"No results found for '{query}'")
            return

        content = f"_Search Results for '{query}'_\n\n"
        for result in results[:20]:  # Limit to 20 results
            name = result.get("name", "")
            package = result.get("package", "")
            title = result.get("title", "")
            content += f"  {name} ({package})\n"
            content += f"    {title}\n\n"

        if self._content:
            self._content.set_content(content)

    def _show_demo_help(self, topic: str) -> None:
        """Show demo help content."""
        demo_content = f"""
_Help for '{topic}'_

(Demo Mode - Not connected to R session)

This is a placeholder help page. When connected to an R session,
this would show the actual R documentation for '{topic}'.

_Usage_

  {topic}(...)

_Arguments_

  ...     Arguments passed to the function

_Details_

Connect to an R session to see the full documentation.

_See Also_

  help, ?{topic}

_Examples_

  # Example usage
  {topic}()
"""
        if self._content:
            self._content.set_content(demo_content)

    def _show_error(self, message: str) -> None:
        """Show an error message."""
        if self._content:
            self._content.set_content(f"Error: {message}")

    async def action_focus_search(self) -> None:
        """Focus the search input."""
        if self._search:
            self._search.focus()

    async def action_back(self) -> None:
        """Navigate back in history."""
        if self._history_pos > 0:
            self._history_pos -= 1
            topic = self._history[self._history_pos]
            await self._do_search(topic)

    async def action_forward(self) -> None:
        """Navigate forward in history."""
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            topic = self._history[self._history_pos]
            await self._do_search(topic)

    async def action_home(self) -> None:
        """Go to help home."""
        self._show_home()

    async def show_help(self, topic: str, package: Optional[str] = None) -> None:
        """Public method to show help for a topic."""
        if self._header:
            self._header.set_topic(topic)

        self._history.append(topic)
        self._history_pos = len(self._history) - 1

        await self._load_help(topic, package)
