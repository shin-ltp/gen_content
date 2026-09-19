# Agent Environment

## Python Runtime

All Python execution in this repository MUST use a project-local environment.

| Purpose | Executable |
|---|---|
| Default project Python; one-off generated scripts, file batch edits, and analysis | `C:\my_project\gen-contents\.venv\Scripts\python.exe` |
| Dedicated Fish Speech runtime | `C:\my_project\gen-contents\tools\fishaudio-s2-pro\fish-speech\.venv\Scripts\python.exe` |

Do not use `%APPDATA%\uv\python\...` or a uv trampoline as the Python entry point.

If Python must be installed or refreshed, set both variables before running `uv`:

```powershell
$env:UV_CACHE_DIR = 'C:\my_project\gen-contents\.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = 'C:\my_project\gen-contents\.uv-python'
```

The default environment is Python 3.12.13 with pip installed. It is intentionally small;
task-specific native dependencies belong in the relevant dedicated environment.
