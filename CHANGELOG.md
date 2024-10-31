# Changelog

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
