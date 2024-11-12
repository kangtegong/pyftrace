# Changelog

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
