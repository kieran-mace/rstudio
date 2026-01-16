# RStudio TUI

A Terminal User Interface (TUI) for RStudio, providing a full-featured R development environment in your terminal.

## Features

- **R Console** - Interactive R REPL with command history and syntax highlighting
- **Source Editor** - Edit R scripts with syntax highlighting and line numbers
- **File Browser** - Navigate your project files
- **Environment Viewer** - Inspect R objects and variables
- **Help System** - Browse R documentation
- **Command History** - Search and re-run previous commands
- **Package Manager** - View and manage R packages
- **Output Viewer** - View R output, errors, and plot references

## Installation

### From Source

```bash
cd src/tui
pip install -e .
```

### Using pip

```bash
pip install rstudio-tui
```

## Usage

### Basic Usage

```bash
# Connect to RStudio session on default port (8787)
rstudio-tui

# Connect to specific port
rstudio-tui -p 8888

# Start in specific directory
rstudio-tui -w ~/projects/myproject

# Run in demo mode (no R session required)
rstudio-tui --demo
```

### With RStudio Server

If you have RStudio Server running, connect to it:

```bash
rstudio-tui -h localhost -p 8787
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F1 | Focus Console |
| F2 | Focus Editor |
| F3 | Focus File Browser |
| F4 | Focus Environment |
| F5 | Focus Help |
| F6 | Toggle History Panel |
| F7 | Toggle Packages Panel |
| Ctrl+Q | Quit |
| Ctrl+S | Save File |
| Ctrl+N | New File |
| Ctrl+Enter | Run Selection (in editor) |

### Console Shortcuts

| Key | Action |
|-----|--------|
| Up/Down | Navigate history |
| Tab | Code completion |
| Ctrl+C | Interrupt |
| Ctrl+L | Clear console |

### Editor Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+S | Save |
| Ctrl+Enter | Run current line |
| Ctrl+Shift+Enter | Run all |
| Ctrl+/ | Toggle comment |

## Architecture

The TUI connects to the same rsession backend used by RStudio Desktop and Server. Communication happens via JSON-RPC over HTTP, using the same protocol as the web interface.

```
┌─────────────────────────────────────┐
│         RStudio TUI (Python)         │
│  ┌─────────┬─────────┬─────────┐    │
│  │ Console │ Editor  │ Browser │    │
│  ├─────────┼─────────┼─────────┤    │
│  │  Help   │ Environ │ History │    │
│  └─────────┴─────────┴─────────┘    │
└────────────────┬────────────────────┘
                 │ JSON-RPC / HTTP
                 ▼
┌─────────────────────────────────────┐
│           rsession (C++)             │
│  ┌─────────────────────────────────┐│
│  │     84+ Session Modules          ││
│  └─────────────────────────────────┘│
│  ┌─────────────────────────────────┐│
│  │        R Interpreter             ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `RSTUDIO_SESSION_HOST` | rsession host address |
| `RSTUDIO_SESSION_PORT` | rsession port number |
| `R_HOME` | R installation directory |

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Code Style

```bash
black rstudio_tui/
ruff check rstudio_tui/
mypy rstudio_tui/
```

## Requirements

- Python 3.9+
- textual >= 0.47.0
- httpx >= 0.26.0
- rich >= 13.7.0

## License

AGPL-3.0 (same as RStudio)

## Contributing

Contributions are welcome! Please see the main RStudio contributing guidelines.
