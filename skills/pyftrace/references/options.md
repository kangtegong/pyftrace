# pyftrace options

    python -m pyftrace [options] script.py [script args ...]
    python -m pyftrace [options] -m module [module args ...]

Options of pyftrace come first.  The first argument that is not an
option is the script; with `-m`, the argument after it is the module.
Everything after the script or module is passed to the traced program
untouched, so `-v` after `-m pytest` is pytest's `-v`.

## Limiting the trace

| Option | Meaning |
| --- | --- |
| `-n LINES`, `--max-lines LINES` | Print at most LINES trace lines, then one `... trace truncated after LINES lines` line.  The program keeps running to its end.  The `Running ...` header is not counted. |
| `-d DEPTH`, `--depth DEPTH` | Print calls up to DEPTH levels deep.  Depth 1 is the outermost traced call.  With `-f`, depth 1 is the selected function. |
| `-c`, `--collapse` | When a call prints exactly the same lines as the call before it at the same level (same function, same calls below it, same results, and with `-a` the same arguments), print it once followed by `... repeated N more times`. |

## Selecting functions

| Option | Meaning |
| --- | --- |
| `-f NAME`, `--function NAME` | Trace only calls of NAME and everything called under them.  Repeatable: any of the names starts a trace. |
| `-e NAME`, `--exclude-function NAME` | Leave out calls of NAME and everything called under them.  Repeatable. |
| `-F PATH`, `--file PATH` | Trace only functions defined in PATH.  Repeatable. |
| `-E PATH`, `--exclude-file PATH` | Leave out functions defined in PATH.  Repeatable. |

NAME is the bare name of a function or method: `total`, not
`Cart.total` or `shop.cart.total`.  Every function with that name
matches; use `-F` to tell two of them apart.

PATH is one of:

- a file: `shop/cart.py`
- a directory, meaning every file under it: `shop`
- a glob: `'shop/*.py'` (quote it)
- a module or package name: `shop.cart`

`-f` and `-F` differ.  `-f total` shows `total` and everything it
calls, whatever file that is in.  `-F shop/cart.py` shows the functions
defined in that file and nothing they call elsewhere.

An empty trace with `-f` means no function of that name ran.  That is
either the answer to your question or a misspelt name: check the name
with grep before concluding the function is never called.

## What a line shows

| Option | Meaning |
| --- | --- |
| `-a`, `--argument` | Add the arguments to each `Called` line, as `name=value` pairs. |
| `-p`, `--path` | Add file paths: `Called f@FILE:DEFLINE from CALLERFILE:LINE`, and ` @ FILE` on return lines. |
| `-v`, `--verbose` | Also trace built-in functions and installed packages.  The standard library stays out, and so do the finders and loaders that packages add to the import system.  Built-ins have no return value in the trace.  Slow on Python 3.8 to 3.11. |

Values are printed with `repr()`, on one line, cut at 200 characters.
An object without a useful `repr` shows as `<shop.cart.Cart object at
0x...>`; that still tells you which object it is across lines.

## Other output

| Option | Meaning |
| --- | --- |
| `-r`, `--report` | Print no trace.  When the program ends, print each function's total time and call count, slowest first.  Printed also when the program ends with `sys.exit()` or an exception. |
| `--format json` | Print each event as one JSON object per line.  Applies to the report too. |
| `-o FILE`, `--output FILE` | Write the trace or report to FILE.  FILE is emptied first and written line by line, so it can be read while the program runs. |
| `-V`, `--version` | Print the version. |

## Streams and exit status

- The trace goes to standard output, mixed with whatever the program
  prints there, in the order things happen.  Use `-o` to keep them
  apart.
- Standard error and standard input belong to the program.
- The exit status is the program's own: a failing test run exits 1
  under pyftrace too.
- If the reader of the output goes away (`... | head -20`), pyftrace
  stops printing and the program runs on to its end.  Prefer `-n 20`:
  it does the same without relying on the pipe.

## Combinations that work well

| Goal | Options |
| --- | --- |
| First look at a program | `-c -d 3 -n 100` |
| One function in detail | `-a -f NAME -n 200` |
| Just the calls of one function and their results | `-a -f NAME -d 1` |
| One module's part in the run | `-F package.module -n 200` |
| Hide a noisy helper | `-e log -e debug` |
| Into a library, bounded | `-v -F requests -d 4 -n 200` |
| Complete trace for searching | `-a -p -o /tmp/trace.txt` |
| Hot spots | `-r` |
