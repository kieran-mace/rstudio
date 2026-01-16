"""
RStudio TUI Widgets

Collection of widgets for the RStudio TUI interface.
"""

from rstudio_tui.widgets.console import ConsoleWidget
from rstudio_tui.widgets.editor import EditorWidget
from rstudio_tui.widgets.file_browser import FileBrowserWidget
from rstudio_tui.widgets.environment import EnvironmentWidget
from rstudio_tui.widgets.help_viewer import HelpViewerWidget
from rstudio_tui.widgets.history import HistoryWidget
from rstudio_tui.widgets.packages import PackagesWidget
from rstudio_tui.widgets.output import OutputWidget
from rstudio_tui.widgets.status_bar import StatusBarWidget

__all__ = [
    "ConsoleWidget",
    "EditorWidget",
    "FileBrowserWidget",
    "EnvironmentWidget",
    "HelpViewerWidget",
    "HistoryWidget",
    "PackagesWidget",
    "OutputWidget",
    "StatusBarWidget",
]
