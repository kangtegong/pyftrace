# Changelog

## [0.4.0] - 2026-11-18

### Added
- Options that bound and shape the trace:
  - `-n`/`--max-lines`: stop printing after a number of lines.
  - `-c`/`--collapse`: print repeated calls once, with a repeat count.
  - `-F`/`--file`, `-E`/`--exclude-file`: trace only, or leave out, the functions of a file, directory, glob or module.
  - `--format json`: one JSON object per trace event.
  - `-m MODULE`: run and trace a module, like `python -m`.
  - `python -m pyftrace`: run pyftrace with an interpreter of your choice.
- Raised exceptions appear in the trace as `Raised` lines.
- Threads and child processes are traced; their lines are marked with `[tid N]` and `[pid N]`.
- A skill for AI coding agents (`skills/pyftrace/`) and Claude Code plugin files to install it.
- New examples: Django, PyTorch, threads, processes, exceptions, loops, callbacks and generators.
- Tests for the options, the TUI and the examples.

### Changed
- `-f`/`--function` and `-e`/`--exclude-function` can be repeated.
- Options of pyftrace must come before the script. Everything after the script is passed to it, options included, so `pyftrace script.py --verbose` now gives `--verbose` to the script.
- A program that dies of an exception prints its own traceback, without the frames of pyftrace.
- `-o`/`--output` writes the trace only to the file; the traced program's own output stays on the terminal.
- Class and module bodies are no longer shown as calls.
- Arguments and return values are cut to one line of at most 200 characters.
- Library code is skipped much more cheaply, so programs that use large libraries run far faster under pyftrace.
- The package no longer installs a top-level `tests` package.

### Fixed
- `-r`/`--report` printed nothing when the program ended with `sys.exit()` or an exception, as every pytest run does.
- `pyftrace ... | head` raised `BrokenPipeError` inside the traced program.
- On Python 3.12 and later, generators and coroutines resumed by an exception (a failed `await`, a cancelled task, `throw()`, `close()`) were missing from the trace.
- On Python 3.12 and later, pyftrace occupied the `sys.monitoring` tool id of coverage tools.
- Scripts could not be given arguments that start with `-`.
- Quitting the TUI on Linux ended with a traceback.
- CI and the release workflow run on current GitHub runners again.

---


## [0.3.1] - 2024-12-23

### Added
- Introduce `-d`/`--depth` option:
  - limit the tracing output to a specified call depth.

### Changed
- Change the output indentation.
  - Changed to have at least one indentation by default when a trace is started.
  - To distinguish it from the `print` statement of traced script.

---


## [0.3.0] - 2024-12-19

### Added
- New Examples:
  - `examples/requests_example.py`: Demonstrates tracing HTTP requests made via `requests.get()`.
  - `examples/torch_example.py`: Demonstrates tracing with the `torch` library.
- Enhanced Tracing Logic:
  - Introduced logic to detect if an external function call is triggered by user script code beyond the import phase.
  - Verbose mode (`-v`) now also traces standard library functions, not just built-ins.

### Changed
- ★ Support Python Version 3.8+ (Wider Python Version Support):
  - Lowered the minimum required Python version from 3.12 to 3.8. On Python 3.8~3.11, `sys.setprofile` is used; on 3.12 and above, `sys.monitoring` is used.
- CI Configuration:
  - Simplified GitHub Actions CI matrix to use only `ubuntu-latest` for testing, removing Windows and macOS from the test matrix.
- Codebase Refinements:
  - Consolidated and refactored the tracing logic to be more maintainable.
  - Merged `PyftraceBase` into `tracer.py` and refactored engines (`pyftrace_monitoring.py`, `pyftrace_setprofile.py`) to import from it directly.

### Fixed
- Top-level External Calls:
  - Fixed an issue where top-level external library calls would not appear in the trace because tracing started only after a call in the user script.
    - Now caller frames are checked: if the calling frame belongs to the user script after imports, tracing starts immediately.
- Normalization of Paths and Encodings:
  - Ensured consistent path normalization and line ending handling.

---

## [0.2.0] - 2024-11-11

### Added
- TUI support start!
  - Added `tui.py` using `curses` for terminal-based UI.
  - Supports Page Up, Page Down, Home, and End keys for scrolling through trace data.
  - New example script `examples/recursives.py` for testing deep trace depth in TUI.
- Argument handling for traced scripts:
  - `pyftrace` now supports passing additional arguments to traced scripts in both CLI and TUI modes.
- Cross-platform testing on GitHub Actions:
  - Added workflows for testing on Ubuntu, Windows, and macOS.

### Changed
- Swapped short options for `verbose` and `version` flags:
  - `verbose` now uses `-v` (lowercase), and `version` uses `-V` (uppercase).
- Documentation updates:
  - README workflow status badges.
  - README Installation instructions for Windows users (noting `windows-curses`).

### Fixed
- Function call parsing logic updated for Windows to handle backslashes in paths.

## [0.1.2] - 2024-11-01

### Added
- GitHub Workflows.
  - Introduced `push-test.yml` workflow to automatically run tests on every push.
  - Added `python-publish.yml` workflow for Python package publishing.

### Changed
- Dynamic Versioning in Tests.
  - Refactored tests in `runtests.py` to dynamically retrieve the `__version__` from `pyftrace/__init__.py`.

---

## [0.1.1] - 2024-10-31

### Added
- Test suite for `pyftrace` (`runtests.py`).
  - Usage example for running tests:
    ```bash
    $ python3.12 tests/runtests.py
    ```
- `-v`, `--version` option to display the current version of `pyftrace`.
    ```bash
    $ pyftrace -v
    pyftrace version 0.1.1
    $ pyftrace --version
    pyftrace version 0.1.1
    ```

### Changed
- Renamed class `SimplePyftrace` to `Pyftrace`.

### Fixed
- Aligned the printed output for called and returned function traces to have consistent depth levels for readability.
- Updated related test code to reflect these alignment changes.

---

## [0.1.0] - 2024-10-26

- Initial release of `pyftrace`.
