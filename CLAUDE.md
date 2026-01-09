# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python 3.12+ desktop application using Tkinter for Android engineering diagnostics. The app provides network diagnostics, logcat viewing, and device performance monitoring via ADB (Android Debug Bridge).

## Running the Application

```bash
python main.py
```

## Architecture

**MVC-like pattern with Service layer:**

```
MainWindow (gui/main_window.py)
├── Tab: NetworkTab -> NetworkService
├── Tab: LogcatTab  -> LogcatService
└── Tab: MonitorTab -> ADBManager (direct calls)
```

### Key Layers

- **Core (`androidToolbox/core/adb.py`)**: `ADBManager` class handles all ADB operations - execute commands, stream logcat, detect bundled executables
- **Services (`androidToolbox/services/`)**: Business logic separated from UI
- **GUI (`gui/`)**: View layer - `main_window.py` is the controller, tabs are in `gui/tab/`

### Key Patterns

- **Threading**: Background threads handle blocking ADB operations; UI updates via `tk.after()` polling
- **Service/UI Communication**: Services use `queue.Queue` for thread-safe data passing
- **Lazy Loading**: Tabs start/stop background tasks on tab switch

## Development Notes

- All ADB commands should go through `ADBManager` in `androidToolbox/core/adb.py`
- Background workers use `threading.Event` for graceful stopping
- UI files in `gui/tab/` but imported as `gui.tabs` module
- Some legacy files (`logcat.py`, `monitor.py`) in `services/` contain mixed UI/service logic
