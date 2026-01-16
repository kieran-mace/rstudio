"""
Environment Viewer Widget

Displays R environment objects with:
- Variable names and types
- Value previews
- Object inspection
- Memory usage
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from rstudio_tui.client import RSessionClient


@dataclass
class EnvironmentObject:
    """Represents an object in the R environment."""

    name: str
    type: str
    class_name: str
    length: int
    size: int
    value: str
    expandable: bool = False


class EnvironmentHeader(Static):
    """Header showing environment name and controls."""

    DEFAULT_CSS = """
    EnvironmentHeader {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, environment: str = "Global Environment", **kwargs):
        super().__init__(**kwargs)
        self.environment = environment

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        self.update(f"Environment: {self.environment}")

    def set_environment(self, name: str) -> None:
        self.environment = name
        self._update_display()


class EnvironmentTable(DataTable):
    """Table displaying environment objects."""

    DEFAULT_CSS = """
    EnvironmentTable {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._objects: List[EnvironmentObject] = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("Name", "Type", "Value", "Size")
        # Set column widths
        self.columns["Name"].width = 20
        self.columns["Type"].width = 15
        self.columns["Value"].width = 30
        self.columns["Size"].width = 10

    def set_objects(self, objects: List[EnvironmentObject]) -> None:
        """Update the table with new objects."""
        self._objects = objects
        self.clear()

        for obj in objects:
            name_text = Text(obj.name)
            type_text = Text(obj.class_name or obj.type, style="cyan")
            value_text = Text(obj.value[:30] + "..." if len(obj.value) > 30 else obj.value)
            size_text = Text(self._format_size(obj.size), style="dim")

            self.add_row(name_text, type_text, value_text, size_text, key=obj.name)

    @staticmethod
    def _format_size(size: int) -> str:
        """Format size in bytes to human-readable string."""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"

    def get_selected_object(self) -> Optional[EnvironmentObject]:
        """Get the currently selected object."""
        if self.cursor_row is not None and 0 <= self.cursor_row < len(self._objects):
            return self._objects[self.cursor_row]
        return None


class EnvironmentWidget(Vertical):
    """
    Environment viewer widget showing R objects.

    Features:
    - List all objects in current environment
    - Show type, size, and value preview
    - Inspect objects in detail
    - Remove objects
    - Switch between environments
    """

    DEFAULT_CSS = """
    EnvironmentWidget {
        height: 100%;
        border: solid $secondary;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("enter", "inspect", "Inspect", show=True),
        Binding("d", "delete", "Delete", show=False),
        Binding("c", "clear_all", "Clear All", show=False),
    ]

    def __init__(
        self,
        client: Optional[RSessionClient] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self._header: Optional[EnvironmentHeader] = None
        self._table: Optional[EnvironmentTable] = None
        self._current_env: str = "R_GlobalEnv"
        self._objects: List[EnvironmentObject] = []

    def compose(self) -> ComposeResult:
        yield EnvironmentHeader()
        yield EnvironmentTable()

    def on_mount(self) -> None:
        self._header = self.query_one(EnvironmentHeader)
        self._table = self.query_one(EnvironmentTable)

        # Start with demo data if not connected
        if not self.client:
            self._load_demo_data()
        else:
            asyncio.create_task(self.refresh())

    def _load_demo_data(self) -> None:
        """Load demo data for testing."""
        demo_objects = [
            EnvironmentObject(
                name="x",
                type="numeric",
                class_name="numeric",
                length=1,
                size=56,
                value="42",
            ),
            EnvironmentObject(
                name="data",
                type="data.frame",
                class_name="data.frame",
                length=100,
                size=8960,
                value="100 obs. of 5 variables",
                expandable=True,
            ),
            EnvironmentObject(
                name="model",
                type="lm",
                class_name="lm",
                length=12,
                size=45280,
                value="Linear Model",
                expandable=True,
            ),
            EnvironmentObject(
                name="text",
                type="character",
                class_name="character",
                length=1,
                size=112,
                value='"Hello, World!"',
            ),
            EnvironmentObject(
                name="vec",
                type="integer",
                class_name="integer",
                length=10,
                size=96,
                value="1, 2, 3, 4, 5, ...",
            ),
        ]
        self._objects = demo_objects
        if self._table:
            self._table.set_objects(demo_objects)

    async def refresh(self) -> None:
        """Refresh the environment list."""
        if not self.client:
            return

        try:
            response = await self.client.list_environment()
            if response.success and response.result:
                objects = []
                for item in response.result:
                    obj = EnvironmentObject(
                        name=item.get("name", ""),
                        type=item.get("type", ""),
                        class_name=item.get("class", ""),
                        length=item.get("length", 0),
                        size=item.get("size", 0),
                        value=item.get("value", ""),
                        expandable=item.get("expandable", False),
                    )
                    objects.append(obj)

                self._objects = objects
                if self._table:
                    self._table.set_objects(objects)
        except Exception as e:
            self.notify(f"Refresh error: {e}", severity="error")

    async def action_refresh(self) -> None:
        """Refresh action handler."""
        await self.refresh()
        self.notify("Environment refreshed")

    async def action_inspect(self) -> None:
        """Inspect the selected object."""
        if not self._table:
            return

        obj = self._table.get_selected_object()
        if not obj:
            return

        if self.client:
            try:
                response = await self.client.get_object_contents(obj.name)
                if response.success:
                    # Show in notification for now
                    # In a full implementation, this would open a detail view
                    content = str(response.result)[:200]
                    self.notify(f"{obj.name}: {content}")
            except Exception as e:
                self.notify(f"Inspect error: {e}", severity="error")
        else:
            self.notify(f"Inspecting: {obj.name} ({obj.class_name})")

    async def action_delete(self) -> None:
        """Delete the selected object."""
        if not self._table:
            return

        obj = self._table.get_selected_object()
        if not obj:
            return

        if self.client:
            try:
                response = await self.client.remove_objects([obj.name])
                if response.success:
                    await self.refresh()
                    self.notify(f"Removed: {obj.name}")
                else:
                    self.notify(f"Failed to remove: {response.error_message}", severity="error")
            except Exception as e:
                self.notify(f"Delete error: {e}", severity="error")
        else:
            self.notify(f"Would delete: {obj.name}")

    async def action_clear_all(self) -> None:
        """Clear all objects from environment."""
        if self.client:
            # Get all object names and remove them
            names = [obj.name for obj in self._objects]
            if names:
                try:
                    response = await self.client.remove_objects(names)
                    if response.success:
                        await self.refresh()
                        self.notify("Environment cleared")
                except Exception as e:
                    self.notify(f"Clear error: {e}", severity="error")
        else:
            self.notify("Would clear all objects")

    async def set_environment(self, name: str) -> None:
        """Switch to a different environment."""
        self._current_env = name
        if self._header:
            self._header.set_environment(name)

        if self.client:
            try:
                await self.client.set_environment(name)
                await self.refresh()
            except Exception as e:
                self.notify(f"Environment switch error: {e}", severity="error")
