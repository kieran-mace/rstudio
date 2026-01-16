"""
Packages Widget

Package manager for R with:
- List installed packages
- Search available packages
- Install/remove packages
- Load/unload packages
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static, TabbedContent, TabPane

if TYPE_CHECKING:
    from rstudio_tui.client import RSessionClient


@dataclass
class PackageInfo:
    """Information about an R package."""

    name: str
    version: str
    title: str
    loaded: bool = False
    installed: bool = True


class PackageHeader(Static):
    """Header for the packages panel."""

    DEFAULT_CSS = """
    PackageHeader {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self.update("Packages")


class PackageSearchInput(Input):
    """Search input for packages."""

    DEFAULT_CSS = """
    PackageSearchInput {
        dock: top;
        height: 1;
        margin: 0;
        border: none;
        background: $surface;
    }
    """

    def __init__(self, on_search: Optional[callable] = None, **kwargs):
        super().__init__(placeholder="Search packages...", **kwargs)
        self._on_search = on_search

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if self._on_search:
            self._on_search(self.value)


class PackageTable(DataTable):
    """Table displaying packages."""

    DEFAULT_CSS = """
    PackageTable {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._packages: List[PackageInfo] = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("", "Package", "Version", "Title")
        # Set column widths
        self.columns[""].width = 3  # Status indicator
        self.columns["Package"].width = 20
        self.columns["Version"].width = 12
        self.columns["Title"].width = 40

    def set_packages(self, packages: List[PackageInfo]) -> None:
        """Update the table with packages."""
        self._packages = packages
        self.clear()

        for pkg in packages:
            # Status indicator
            if pkg.loaded:
                status = Text("[*]", style="bold green")
            elif pkg.installed:
                status = Text("[ ]", style="dim")
            else:
                status = Text("   ", style="dim")

            name = Text(pkg.name)
            version = Text(pkg.version, style="cyan")
            title = Text(pkg.title[:40] if len(pkg.title) > 40 else pkg.title, style="dim")

            self.add_row(status, name, version, title, key=pkg.name)

    def get_selected_package(self) -> Optional[PackageInfo]:
        """Get the currently selected package."""
        if self.cursor_row is not None and 0 <= self.cursor_row < len(self._packages):
            return self._packages[self.cursor_row]
        return None


class PackagesWidget(Vertical):
    """
    Packages widget for managing R packages.

    Features:
    - List installed packages
    - Show loaded packages
    - Search packages
    - Install/remove packages
    - Load/unload packages
    """

    DEFAULT_CSS = """
    PackagesWidget {
        height: 100%;
        border: solid $secondary;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("l", "load_package", "Load", show=True),
        Binding("u", "unload_package", "Unload", show=False),
        Binding("i", "install_package", "Install", show=False),
        Binding("d", "remove_package", "Remove", show=False),
        Binding("slash", "focus_search", "Search", show=True),
    ]

    def __init__(
        self,
        client: Optional[RSessionClient] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self._header: Optional[PackageHeader] = None
        self._search: Optional[PackageSearchInput] = None
        self._table: Optional[PackageTable] = None
        self._all_packages: List[PackageInfo] = []
        self._filtered_packages: List[PackageInfo] = []

    def compose(self) -> ComposeResult:
        yield PackageHeader()
        yield PackageSearchInput(on_search=self._handle_search)
        yield PackageTable()

    def on_mount(self) -> None:
        self._header = self.query_one(PackageHeader)
        self._search = self.query_one(PackageSearchInput)
        self._table = self.query_one(PackageTable)

        # Load packages
        if self.client:
            asyncio.create_task(self.refresh())
        else:
            self._load_demo_packages()

    def _load_demo_packages(self) -> None:
        """Load demo packages for testing."""
        demo_packages = [
            PackageInfo("base", "4.3.2", "The R Base Package", loaded=True),
            PackageInfo("stats", "4.3.2", "The R Stats Package", loaded=True),
            PackageInfo("graphics", "4.3.2", "The R Graphics Package", loaded=True),
            PackageInfo("utils", "4.3.2", "The R Utils Package", loaded=True),
            PackageInfo("datasets", "4.3.2", "The R Datasets Package", loaded=True),
            PackageInfo("methods", "4.3.2", "Formal Methods and Classes", loaded=True),
            PackageInfo("ggplot2", "3.4.4", "Create Elegant Data Visualisations", loaded=True),
            PackageInfo("dplyr", "1.1.4", "A Grammar of Data Manipulation", loaded=False),
            PackageInfo("tidyr", "1.3.0", "Tidy Messy Data", loaded=False),
            PackageInfo("readr", "2.1.4", "Read Rectangular Text Data", loaded=False),
            PackageInfo("stringr", "1.5.1", "Simple, Consistent Wrappers for String Operations", loaded=False),
            PackageInfo("purrr", "1.0.2", "Functional Programming Tools", loaded=False),
            PackageInfo("tibble", "3.2.1", "Simple Data Frames", loaded=False),
            PackageInfo("forcats", "1.0.0", "Tools for Working with Categorical Variables", loaded=False),
            PackageInfo("lubridate", "1.9.3", "Make Dealing with Dates a Little Easier", loaded=False),
        ]

        self._all_packages = demo_packages
        self._filtered_packages = demo_packages.copy()
        self._update_table()

    async def refresh(self) -> None:
        """Refresh package list from rsession."""
        if not self.client:
            return

        try:
            response = await self.client.get_package_state()
            if response.success and response.result:
                packages = []
                package_list = response.result.get("packages", [])
                loaded_packages = set(response.result.get("loaded", []))

                for pkg_data in package_list:
                    pkg = PackageInfo(
                        name=pkg_data.get("name", ""),
                        version=pkg_data.get("version", ""),
                        title=pkg_data.get("title", ""),
                        loaded=pkg_data.get("name", "") in loaded_packages,
                        installed=True,
                    )
                    packages.append(pkg)

                self._all_packages = packages
                self._filtered_packages = packages.copy()
                self._update_table()
        except Exception as e:
            self.notify(f"Package refresh error: {e}", severity="error")

    def _update_table(self) -> None:
        """Update the package table."""
        if self._table:
            # Sort: loaded first, then alphabetically
            sorted_packages = sorted(
                self._filtered_packages,
                key=lambda p: (not p.loaded, p.name.lower()),
            )
            self._table.set_packages(sorted_packages)

    def _handle_search(self, query: str) -> None:
        """Filter packages based on search query."""
        query = query.lower().strip()

        if not query:
            self._filtered_packages = self._all_packages.copy()
        else:
            self._filtered_packages = [
                pkg
                for pkg in self._all_packages
                if query in pkg.name.lower() or query in pkg.title.lower()
            ]

        self._update_table()

    async def action_refresh(self) -> None:
        """Refresh action handler."""
        await self.refresh()
        self.notify("Packages refreshed")

    async def action_load_package(self) -> None:
        """Load the selected package."""
        if not self._table:
            return

        pkg = self._table.get_selected_package()
        if not pkg:
            return

        if pkg.loaded:
            self.notify(f"{pkg.name} is already loaded")
            return

        if self.client:
            try:
                response = await self.client.load_package(pkg.name)
                if response.success:
                    pkg.loaded = True
                    self._update_table()
                    self.notify(f"Loaded: {pkg.name}")
                else:
                    self.notify(f"Failed to load: {response.error_message}", severity="error")
            except Exception as e:
                self.notify(f"Load error: {e}", severity="error")
        else:
            self.notify(f"Would load: {pkg.name}")

    async def action_unload_package(self) -> None:
        """Unload the selected package."""
        if not self._table:
            return

        pkg = self._table.get_selected_package()
        if not pkg:
            return

        if not pkg.loaded:
            self.notify(f"{pkg.name} is not loaded")
            return

        if self.client:
            try:
                response = await self.client.unload_package(pkg.name)
                if response.success:
                    pkg.loaded = False
                    self._update_table()
                    self.notify(f"Unloaded: {pkg.name}")
                else:
                    self.notify(f"Failed to unload: {response.error_message}", severity="error")
            except Exception as e:
                self.notify(f"Unload error: {e}", severity="error")
        else:
            self.notify(f"Would unload: {pkg.name}")

    async def action_install_package(self) -> None:
        """Install a new package."""
        # Would need an input dialog for package name
        self.notify("Use install.packages() in console to install packages")

    async def action_remove_package(self) -> None:
        """Remove the selected package."""
        if not self._table:
            return

        pkg = self._table.get_selected_package()
        if not pkg:
            return

        if self.client:
            try:
                response = await self.client.remove_packages([pkg.name])
                if response.success:
                    await self.refresh()
                    self.notify(f"Removed: {pkg.name}")
                else:
                    self.notify(f"Failed to remove: {response.error_message}", severity="error")
            except Exception as e:
                self.notify(f"Remove error: {e}", severity="error")
        else:
            self.notify(f"Would remove: {pkg.name}")

    async def action_focus_search(self) -> None:
        """Focus the search input."""
        if self._search:
            self._search.focus()
