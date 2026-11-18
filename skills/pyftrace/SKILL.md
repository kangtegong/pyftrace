---
name: pyftrace
description: Use when a Python program or test gives a wrong result, raises an exception from a place you cannot find, never calls the function you expected, or runs slowly, and reading the source has not explained why. Also use to learn how an unfamiliar codebase or framework reaches a piece of code. pyftrace runs the program and prints the functions that were actually called, in order, as a tree, with arguments, return values and raised exceptions. It needs no change to the code, so reach for it before adding print statements and whenever a debugger would need a breakpoint you do not yet know where to put.
---

# pyftrace

pyftrace runs a Python script, module or test and prints every function
call and return as an indented tree.  Reading source tells you what
could happen.  A trace tells you what did happen: which functions ran,
in what order, what they were given and what they gave back.

## When it is the right tool

| You want to know | Use |
| --- | --- |
| Which path the program took, who called what, what a function returned | pyftrace |
| Where an exception was raised and which function caught it | pyftrace |
| Whether a function ran at all, or how many times | pyftrace |
| Which functions take the time | pyftrace `-r` first, then a sampling profiler if needed |
| The value of a local variable in the middle of a function | a debugger or one print; pyftrace sees only arguments and return values |
| Why a line inside one function computes a wrong value | read that function; the trace has already told you which one it is |

A traceback is one path at one moment.  A trace also shows the calls
that returned normally before things went wrong, and that is usually
where the wrong value came from.

## Setup

Run pyftrace with the interpreter the project runs on, so the program
finds its packages:

    python -m pyftrace -V

This needs pyftrace 0.4.0 or later (Python 3.8 or later).  If the
module is missing or older, install it into that environment with
`python -m pip install -U pyftrace`.  Ask before installing if the
user has not said dependencies may be added.  A `pyftrace` command is
installed too, and is fine when it belongs to the same environment.

pyftrace runs the target for real, side effects included.  Do not trace
a command you would not run directly.

## Running it

    python -m pyftrace [options] script.py [script args ...]
    python -m pyftrace [options] -m module [module args ...]

pyftrace's options go before the script or `-m`.  Everything after
belongs to the traced program.  The trace goes to standard output
together with the program's own output, and the exit status is the
program's.

To trace one test:

    python -m pyftrace -a -m pytest tests/test_cart.py::test_total -x -q
    python -m pyftrace -a -m unittest tests.test_cart.CartTest.test_total

Trace one test, not the suite.  pytest captures output, so the trace of
a failing test appears in its "Captured stdout" section and the trace
of a passing test is hidden: add pytest's `-s`, or write the trace to a
file with pyftrace's `-o`.

## The loop

1. **Say what you expect.**  "`total()` should call `apply_coupon()`,
   which should return 5.4."  A trace only helps when there is something
   to compare it with.
2. **Take the smallest trace that can show it.**  One test or one
   input, filtered to the function in question (`-f`), with arguments
   (`-a`).
3. **Find the first line that differs from what you expected.**  Read
   from the top.  Everything after the first wrong value is a
   consequence of it.
4. **Go one level deeper, or stop.**  If the wrong value comes from a
   callee, that callee is the next suspect: trace it.  If a function
   got the right arguments and returned a wrong value with no wrong
   callee under it, the bug is in that function's own lines.  Read them.
5. **Fix, then take the same trace again.**  The line that was wrong
   must now be right.  A passing test alone does not show that the
   cause you found was the cause.

If two traces have not moved you forward, the expectation in step 1 is
wrong.  Widen the trace (drop `-f`, add `-p`) instead of narrowing it
again.

A function that is missing from the trace is evidence too.  If you
expected `validate()` to run and it does not appear, the bug is in
whatever was supposed to call it.

## Keep the trace small

A trace of a real program can be tens of thousands of lines.  Bound it
from the first run and widen only when needed.

| Option | Effect |
| --- | --- |
| `-n LINES` | Stop printing after LINES lines.  The program runs on to its end. |
| `-d DEPTH` | Print calls up to DEPTH levels deep only. |
| `-c` | Print a call that repeats the one before it once, with a repeat count.  For loops. |
| `-f NAME` | Print only calls of the function NAME and everything under them.  Repeatable. |
| `-e NAME` | Leave out calls of NAME and everything under them.  Repeatable. |
| `-F PATH` | Print only functions defined in PATH: a file, directory, glob or module name.  Repeatable. |
| `-E PATH` | Leave out functions defined in PATH.  Repeatable. |
| `-o FILE` | Write the trace to FILE; the program's output stays on the terminal. |

`-f` and `-e` take the bare function name (`total`, not `Cart.total`).
With `-f`, depth counts from the selected function, so `-f total -d 1`
prints just the calls of `total` and their results.

First look at an unknown program: `-c -d 3 -n 100`.  Zooming in:
`-a -f NAME -n 200`.  When the trace must be complete, write it with
`-o` and search the file with grep instead of reading it whole.

## What is traced

Only the project's own code by default.  The standard library and
installed packages are left out, but the calls they make back into
project code are shown, so a view called by a framework or a callback
called by a library appears in the trace without the framework around
it.

| Option | Effect |
| --- | --- |
| `-a` | Show the arguments of every call. |
| `-p` | Show the file and line where each function is defined and called from.  Use it when names are ambiguous or you need to open the code. |
| `-v` | Trace built-ins and installed packages too, not the standard library.  Far more output and slower; pair it with `-F`, `-f`, `-d` or `-n`. |
| `-r` | Print no trace.  Print total time and call count per function when the program ends. |
| `--format json` | One JSON object per line.  For traces a script will process. |

## Reading a trace

    $ python -m pyftrace -a -f total -m pytest tests/test_cart.py::test_ten -q -s
        Called total (self=<shop.cart.Cart object at 0x10444b530>, coupon='ten') from line 13
            Called subtotal (self=<shop.cart.Cart object at 0x10444b530>) from line 14
            Returning subtotal-> 6.0
            Called apply_coupon (amount=6.0, coupon='ten') from line 16
                Called lookup_rate (coupon='ten') from line 20
                Returning lookup_rate-> 10
            Returning apply_coupon-> -54.0
        Returning total-> -54.0

The test expected 5.4 and got -54.0.  Reading down: `subtotal` returned
6.0, which is right.  `lookup_rate('ten')` returned 10, and a rate
should be a fraction.  That is the first wrong line, so the bug is in
`lookup_rate` or its data, not in `apply_coupon` or `total`, which only
passed the value on.

- Indentation is call depth.
- `Called f (args) from line N`: `f` was called from line N of its
  caller.  The arguments appear with `-a`.  `from line N in MODULE`
  means the caller is library code, such as `threading` or a framework.
- `Returning f-> value`: what `f` returned, cut to one line of at most
  200 characters.
- `Raised f-> Error: message`: an exception left `f`.  The deepest
  `Raised` line is where it was raised.  It propagates up through each
  following `Raised` line, and the first function that shows
  `Returning` again is the one that caught it.
- `... repeated N more times`: `-c` folded identical calls.
- `... trace truncated after N lines`: `-n` was reached; the program
  went on without printing.
- `[tid N]` or `[pid N]` before a line: it ran in another thread or in
  a child process.

`references/output.md` has every line form, the JSON fields, and how
generators and coroutines appear.

## Playbook

**A function returns the wrong value.**  Trace it with its arguments
and find the first wrong line among its callees.

    python -m pyftrace -a -f compute -n 200 script.py

**An exception with an unclear origin, or one that is swallowed.**
Write the whole trace to a file and search for the `Raised` lines.  The
lines above the first one show the arguments that led to it.

    python -m pyftrace -a -o /tmp/trace.txt script.py
    grep -n -B8 -A4 Raised /tmp/trace.txt | head -60

**"Is this even called?" and "how often?"**

    python -m pyftrace -f send_email -d 1 script.py     # each call and result
    python -m pyftrace -r script.py | grep send_email   # the count

**It works for one input and fails for another.**  Trace both and
compare.  The first difference is where the two runs part ways.
Addresses of objects change between runs, so leave `-a` out or strip
them.

    python -m pyftrace -o /tmp/good.txt script.py good-input
    python -m pyftrace -o /tmp/bad.txt script.py bad-input
    diff /tmp/good.txt /tmp/bad.txt | head -40

**It worked before a change.**  The same, across versions: trace on
each commit and diff.

**How does the framework reach my code?**  Project code alone shows the
order of your handlers.  Add `-v` with a filter to see the library
frames in between.

    python -m pyftrace -p -d 4 -n 100 app.py
    python -m pyftrace -v -p -f my_view -d 6 -n 200 app.py

**What does this loop do?**  `-c` folds passes that are identical, so
the shape of the loop and the passes that differ stand out.  Arguments
make every pass differ, so add `-a` only when you want each pass.

    python -m pyftrace -c -f process_batch -n 100 script.py
    python -m pyftrace -a -f process_item -d 1 -n 50 script.py

**What is slow?**  The report lists total time and call count per
function, slowest first.  A function called 10,000 times is as much a
finding as one slow call.

    python -m pyftrace -r script.py | head -20

**Threads, processes, async code, web frameworks, long-running
programs.**  See `references/scenarios.md`.

## Mistakes to avoid

- Tracing a whole test suite or a whole application unbounded.  Pick
  one test or one request, and bound the output.
- Using `-v` without a filter.  A single `import` is thousands of
  library calls.
- Reading a long trace from top to bottom.  Write it with `-o`, grep
  for the function or for `Raised`, and read around the hits.
- Tracing without an expectation.  It produces output, not an answer.
- Trusting timing taken under the tracer as absolute.  Tracing slows
  every call; use `-r` to rank functions, not to quote durations.
- Using `pyftrace tui`.  It is an interactive viewer for a person at a
  terminal.

## Reference

- `references/options.md`: every option, how options combine, exit
  status, output streams.
- `references/output.md`: line forms, JSON fields, generators and
  coroutines, processing a trace with a script.
- `references/scenarios.md`: pytest and unittest, web frameworks,
  async code, threads and processes, programs that read input or do
  not end.
