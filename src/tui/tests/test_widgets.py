"""Tests for TUI widgets."""

import pytest
from pathlib import Path

from rstudio_tui.widgets.console import ConsoleHistory
from rstudio_tui.widgets.environment import EnvironmentObject
from rstudio_tui.widgets.history import HistoryEntry
from rstudio_tui.widgets.packages import PackageInfo
from rstudio_tui.widgets.output import OutputType, OutputEntry

from datetime import datetime


class TestConsoleHistory:
    """Tests for ConsoleHistory class."""

    def test_add_command(self):
        """Test adding commands to history."""
        history = ConsoleHistory()
        history.add("x <- 1")
        history.add("print(x)")
        assert len(history.history) == 2

    def test_add_empty_command(self):
        """Test that empty commands are not added."""
        history = ConsoleHistory()
        history.add("")
        history.add("   ")
        assert len(history.history) == 0

    def test_no_duplicates(self):
        """Test that consecutive duplicates are not added."""
        history = ConsoleHistory()
        history.add("x <- 1")
        history.add("x <- 1")
        assert len(history.history) == 1

    def test_navigate_previous(self):
        """Test navigating to previous commands."""
        history = ConsoleHistory()
        history.add("cmd1")
        history.add("cmd2")
        history.add("cmd3")

        history.start_navigation("")
        assert history.previous() == "cmd3"
        assert history.previous() == "cmd2"
        assert history.previous() == "cmd1"
        assert history.previous() == "cmd1"  # Should stay at oldest

    def test_navigate_next(self):
        """Test navigating to next commands."""
        history = ConsoleHistory()
        history.add("cmd1")
        history.add("cmd2")
        history.add("cmd3")

        history.start_navigation("current")
        history.previous()
        history.previous()
        history.previous()

        assert history.next() == "cmd2"
        assert history.next() == "cmd3"
        assert history.next() == "current"  # Returns to saved input

    def test_reset(self):
        """Test resetting history navigation."""
        history = ConsoleHistory()
        history.add("cmd1")
        history.start_navigation("test")
        history.previous()
        history.reset()

        assert history._position == -1
        assert history._current_input == ""


class TestEnvironmentObject:
    """Tests for EnvironmentObject dataclass."""

    def test_object_creation(self):
        """Test creating an environment object."""
        obj = EnvironmentObject(
            name="x",
            type="numeric",
            class_name="numeric",
            length=1,
            size=56,
            value="42",
        )
        assert obj.name == "x"
        assert obj.type == "numeric"
        assert obj.expandable is False

    def test_expandable_object(self):
        """Test expandable object."""
        obj = EnvironmentObject(
            name="df",
            type="data.frame",
            class_name="data.frame",
            length=100,
            size=8960,
            value="100 obs.",
            expandable=True,
        )
        assert obj.expandable is True


class TestHistoryEntry:
    """Tests for HistoryEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a history entry."""
        entry = HistoryEntry(
            index=1,
            command="library(ggplot2)",
            timestamp=datetime.now(),
        )
        assert entry.index == 1
        assert entry.command == "library(ggplot2)"

    def test_entry_without_timestamp(self):
        """Test entry without timestamp."""
        entry = HistoryEntry(index=1, command="x <- 1")
        assert entry.timestamp is None


class TestPackageInfo:
    """Tests for PackageInfo dataclass."""

    def test_package_creation(self):
        """Test creating package info."""
        pkg = PackageInfo(
            name="ggplot2",
            version="3.4.4",
            title="Create Elegant Data Visualisations",
            loaded=True,
        )
        assert pkg.name == "ggplot2"
        assert pkg.loaded is True
        assert pkg.installed is True

    def test_uninstalled_package(self):
        """Test uninstalled package."""
        pkg = PackageInfo(
            name="newpkg",
            version="1.0.0",
            title="New Package",
            installed=False,
        )
        assert pkg.installed is False
        assert pkg.loaded is False


class TestOutputTypes:
    """Tests for output types."""

    def test_output_type_values(self):
        """Test output type enum values."""
        assert OutputType.OUTPUT.value == "output"
        assert OutputType.ERROR.value == "error"
        assert OutputType.WARNING.value == "warning"

    def test_output_entry(self):
        """Test creating output entry."""
        entry = OutputEntry(
            type=OutputType.ERROR,
            content="Error: object 'x' not found",
            timestamp=datetime.now(),
            source="console",
        )
        assert entry.type == OutputType.ERROR
        assert entry.source == "console"
