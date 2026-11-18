# pyftrace output

## Text

    Running script: examples/exception.py
        Called safe_load (text='x') from line 14
            Called load (text='x') from line 9
                Called parse (text='x') from line 5
                Raised parse-> ValueError: invalid literal for int() with base 10: 'x'
            Raised load-> ValueError: invalid literal for int() with base 10: 'x'
        Returning safe_load-> -1

| Line | Meaning |
| --- | --- |
| `Running script: PATH` / `Running module: NAME` | Header, printed once. |
| `Called f from line N` | `f` was called from line N of the calling function's file. |
| `Called f (a=1, b='x') from line N` | The same with `-a`. |
| `Called f@FILE:DEF from CALLER:N` | The same with `-p`: where `f` is defined and where the call is. |
| `Returning f-> VALUE` | `f` returned VALUE. |
| `Raised f-> TYPE: MESSAGE` | An exception left `f`.  On Python 3.8 to 3.11 the line is just `Raised f`. |
| `... repeated N more times` | With `-c`: the call above happened N more times in a row with the same result. |
| `... trace truncated after N lines` | With `-n`: nothing is printed after this. |
| `[tid N] ...` | The line comes from a thread other than the main one. |
| `[pid N] ...` | The line comes from a child process. |

Each level of indentation is four spaces.  The first traced call is at
depth 1, indented once.

### Reading exceptions

An exception shows as a run of `Raised` lines climbing out of the call
tree.  The deepest one is where it was raised.  The climb ends at the
first function that prints `Returning`: that function caught it.  If
the climb reaches depth 1, nothing caught it and the program's
traceback follows on standard error.

In the example above `parse` raised, `load` let it through, and
`safe_load` caught it and returned -1.  A swallowed exception looks
exactly like this: a `Raised` run that ends in a normal return, with no
traceback anywhere.

### Generators and coroutines

A generator or coroutine prints `Called` each time it is resumed and
`Returning` each time it yields or awaits, so one generator appears
several times:

    Called numbers from line 8
    Returning numbers-> 1          <- yielded 1
    Called numbers from line 8
    Returning numbers-> 2          <- yielded 2
    Called numbers from line 8
    Returning numbers-> None       <- finished

A coroutine that awaits something not yet ready shows
`Returning fetch-> <Future pending>`; its real result is on the last
`Returning` line for that coroutine.  Under an event loop, the lines of
concurrent tasks interleave and resumed coroutines appear at the depth
the loop resumes them from, not under the function that awaited them.

Generator expressions appear as `<genexpr>` and lambdas as `<lambda>`.
Class bodies and module-level code are not shown as calls, but calls
made from module level are, so applying a decorator shows up as a call
of the decorator while the module is being imported.

### Names

A line shows the bare function name.  Two methods with the same name on
different classes look alike; `-a` shows `self`, and `-p` shows the
file and line of the definition.  On Python 3.12 or later a decorated
function shows under the name of the wrapper that actually runs
(often `wrapper`), followed by the wrapped function one level deeper.

## JSON

With `--format json` every line is one object.

    {"event": "start", "script": "examples/exception.py"}
    {"event": "call", "depth": 1, "function": "safe_load", "line": 14, "args": "text='x'"}
    {"event": "raise", "depth": 3, "function": "parse", "exception": "ValueError: invalid literal for int() with base 10: 'x'"}
    {"event": "return", "depth": 1, "function": "safe_load", "value": "-1"}

| `event` | Fields |
| --- | --- |
| `start` | `script` or `module` |
| `call` | `depth`, `function`, `line` (of the call site); with `-a`: `args`; with `-p`: `defined_at` (`FILE:LINE`), `caller_file` |
| `return` | `depth`, `function`, `value` (absent for built-ins); with `-p`: `file` |
| `raise` | `depth`, `function`, `exception` (Python 3.12 or later); with `-p`: `file` |
| `repeat` | `depth`, `count` |
| `truncated` | `max_lines` |
| `report` | `function`, `seconds`, `calls` (with `-r`) |

Any event may carry `tid` and `pid` when it comes from another thread
or a child process.  `args`, `value` and `exception` are strings, the
same text the text format prints.

The program's own output is on standard output too, so write JSON
traces to a file with `-o` and parse that:

    python -m pyftrace --format json -a -o /tmp/trace.jsonl script.py

    import json
    events = [json.loads(line) for line in open("/tmp/trace.jsonl")]
    raised = [e for e in events if e["event"] == "raise"]

Things a script answers faster than reading: how many times each
function was called (`collections.Counter` over `call` events), the
maximum depth reached, every distinct return value of one function, the
call that precedes each `raise`.

## Report

    Function Name	| Total Execution Time	| Call Count
    ---------------------------------------------------------
    run            	| 0.101031 seconds	| 1
    tick           	| 0.033222 seconds	| 1000

Sorted by total time, largest first.  The time of a function includes
the time of everything it calls, so the callers of a slow function are
listed above it.  Look for the lowest function in the list whose time
is still large, and for call counts that are larger than the input
explains.  Times include the overhead of tracing; compare them with
each other, not with a stopwatch.
