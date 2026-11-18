---
name: pyftrace
description: Trace which Python functions a program actually calls, in what order, with what arguments and return values, and where an exception is raised. Use when debugging Python code whose control flow is unclear, when a test or script gives a wrong result and reading the source did not explain it, when exploring how an unfamiliar codebase or framework reaches a given function, or when looking for the functions that take the time.
---

# pyftrace

pyftrace runs a Python script or module and prints every function call
and return as an indented tree.  It answers "what really ran" without
editing the code to add prints.

## Before the first run

    pyftrace -V

The options below need pyftrace 0.4.0 or later and Python 3.8 or later.
If the command is missing or older, install it into the environment the
project runs in:

    pip install -U pyftrace

pyftrace executes the target program for real.  Do not trace a command
you would not run directly (one that deletes data, sends requests to
production, and so on).

## Running it

    pyftrace [options] script.py [script args ...]
    pyftrace [options] -m module [module args ...]

Options go before the script or `-m`; everything after it belongs to
the traced program.  To trace a test:

    pyftrace -n 200 -m pytest tests/test_x.py::test_name -x -q
    pyftrace -n 200 -m unittest tests.test_x.TestCase.test_name

## Always bound the output

A trace of a real program can be very long.  Start small and widen:

| Option | Effect |
| --- | --- |
| `-n LINES` | Stop printing after LINES lines.  The program still runs to the end. |
| `-d DEPTH` | Print only calls up to DEPTH levels deep. |
| `-c` | Print a call that repeats the previous one once, with a repeat count.  Use it for loops. |
| `-f NAME` | Print only calls of function NAME and what it calls.  Repeatable. |
| `-e NAME` | Leave out calls of NAME and what it calls.  Repeatable. |
| `-F PATH` | Print only functions defined in PATH: a file, directory, glob or module name.  Repeatable. |
| `-E PATH` | Leave out functions defined in PATH.  Repeatable. |
| `-o FILE` | Write the trace to FILE instead of the terminal.  The program's own output stays on the terminal. |

A good first run is `pyftrace -c -d 3 -n 100 script.py`.  Then narrow
with `-f` on the function of interest and add `-a`.

With `-o`, search the file with grep or read a part of it instead of
reading it whole.

## What to show

| Option | Effect |
| --- | --- |
| `-a` | Show the arguments of each call. |
| `-p` | Show the file and line of each function and call site. |
| `-v` | Also trace built-ins, the standard library and installed packages.  Much more output and slower: always combine it with `-n`, `-d` or `-F`. |
| `-r` | Print no trace; print total time and call count per function at the end. |
| `--format json` | One JSON object per line instead of text.  Use it when a script will read the trace. |

By default only the project's own code is traced.  Code of the standard
library and of installed packages is left out, but calls it makes back
into project code (a framework calling a view, a callback) are shown.

## Reading the output

    Running script: examples/exception.py
        Called safe_load from line 14
            Called load from line 9
                Called parse from line 5
                Raised parse
            Raised load
        Returning safe_load-> -1

- Indentation is call depth.
- `Called f from line N`: `f` was called from line N of the caller.
- `Returning f-> value`: `f` returned `value`.  Values are cut to one
  line of at most 200 characters.
- `Raised f`: an exception left `f`.  The deepest `Raised` line is where
  it was raised; the function that shows `Returning` after a run of
  `Raised` lines is the one that caught it.  On Python 3.12 or later the
  line also names the exception.
- `... trace truncated after N lines`: `-n` was reached.
- `[tid N]` or `[pid N]` at the start of a line: the call ran in another
  thread or in a child process.

The same events with `--format json -a`:

    {"event": "call", "depth": 1, "function": "safe_load", "line": 13, "args": "text='1'"}
    {"event": "return", "depth": 1, "function": "safe_load", "value": "2"}

The `event` field is `start`, `call`, `return`, `raise` or `truncated`.

## Recipes

Why does this function return the wrong value?

    pyftrace -a -f compute -n 200 script.py

Where is this exception raised, and who catches it?

    pyftrace -o /tmp/trace.txt script.py; grep -n -B5 Raised /tmp/trace.txt

How does the framework reach my code?

    pyftrace -p -d 4 -n 100 app.py           # only project code
    pyftrace -v -p -f my_view -n 200 app.py  # with library code

What is slow?

    pyftrace -r script.py

What does this loop do on each pass?

    pyftrace -c -a -f process_item -n 100 script.py

## Limits

- Only function calls are traced, not lines or variable assignments.
- On Python 3.8 to 3.11, `-v` is slow and `Raised` lines do not name
  the exception.
- `pyftrace tui script.py` opens an interactive viewer.  It needs a
  terminal with a person at it; do not use it from an agent.
