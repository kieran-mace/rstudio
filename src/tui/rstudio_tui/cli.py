"""
RStudio TUI Command Line Interface

Entry point for launching the TUI from the command line.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import click


@click.command()
@click.option(
    "--host",
    "-h",
    default="127.0.0.1",
    help="RStudio session host address",
    show_default=True,
)
@click.option(
    "--port",
    "-p",
    default=8787,
    type=int,
    help="RStudio session port",
    show_default=True,
)
@click.option(
    "--working-dir",
    "-w",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Initial working directory",
)
@click.option(
    "--project",
    "-P",
    type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
    help="Open an RStudio project (.Rproj file or directory)",
)
@click.option(
    "--file",
    "-f",
    "files",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    multiple=True,
    help="File(s) to open in the editor",
)
@click.option(
    "--demo",
    is_flag=True,
    help="Run in demo mode without connecting to rsession",
)
@click.version_option(
    version="0.1.0",
    prog_name="rstudio-tui",
)
def main(
    host: str,
    port: int,
    working_dir: Optional[Path],
    project: Optional[Path],
    files: tuple[Path, ...],
    demo: bool,
) -> None:
    """
    RStudio TUI - Terminal User Interface for RStudio

    Launch RStudio in your terminal with a full-featured text-based interface.

    \b
    Examples:
        rstudio-tui                    # Start with default settings
        rstudio-tui -p 8888            # Connect to session on port 8888
        rstudio-tui -w ~/projects/myproject  # Start in specific directory
        rstudio-tui -P myproject.Rproj # Open an RStudio project
        rstudio-tui -f script.R        # Open a file
        rstudio-tui --demo             # Run without R session (demo mode)

    \b
    Keyboard Shortcuts:
        F1      - Focus Console
        F2      - Focus Editor
        F3      - Focus Files
        F4      - Focus Environment
        F5      - Focus Help
        F6      - Toggle History
        F7      - Toggle Packages
        Ctrl+Q  - Quit
        Ctrl+S  - Save File
        Ctrl+N  - New File
    """
    # Determine working directory
    if working_dir is None:
        if project:
            # If project is a .Rproj file, use its directory
            if project.suffix.lower() == ".rproj":
                working_dir = project.parent
            else:
                working_dir = project
        else:
            working_dir = Path.cwd()

    # Check for environment variables
    env_host = os.environ.get("RSTUDIO_SESSION_HOST")
    env_port = os.environ.get("RSTUDIO_SESSION_PORT")

    if env_host:
        host = env_host
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            click.echo(f"Warning: Invalid RSTUDIO_SESSION_PORT: {env_port}", err=True)

    # Demo mode - don't try to connect
    if demo:
        click.echo("Starting RStudio TUI in demo mode...")
        port = 0  # Signal no connection

    # Import and run the app
    from rstudio_tui.app import RStudioTUI

    app = RStudioTUI(
        host=host,
        port=port if not demo else 0,
        working_dir=working_dir,
    )

    # Run the application
    try:
        app.run()
    except KeyboardInterrupt:
        click.echo("\nRStudio TUI terminated.")
        sys.exit(0)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def launch_with_session(
    session_url: Optional[str] = None,
    working_dir: Optional[Path] = None,
) -> None:
    """
    Launch TUI with automatic session detection.

    This function is intended to be called from the RStudio launcher
    to start the TUI alongside an rsession process.

    Args:
        session_url: URL of the rsession (e.g., "http://127.0.0.1:8787")
        working_dir: Working directory for the session
    """
    import urllib.parse

    host = "127.0.0.1"
    port = 8787

    if session_url:
        parsed = urllib.parse.urlparse(session_url)
        host = parsed.hostname or host
        port = parsed.port or port

    from rstudio_tui.app import run_tui

    run_tui(host=host, port=port, working_dir=working_dir)


if __name__ == "__main__":
    main()
