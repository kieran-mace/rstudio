"""
RStudio TUI - Terminal User Interface for RStudio

This module provides a terminal-based user interface for RStudio,
connecting to the same rsession backend as the web and desktop interfaces.
"""

__version__ = "0.1.0"
__author__ = "Posit Software, PBC"

from rstudio_tui.app import RStudioTUI

__all__ = ["RStudioTUI", "__version__"]
