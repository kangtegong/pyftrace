# pyftrace in common situations

## pytest

    python -m pyftrace -a -m pytest tests/test_cart.py::test_ten -x -q

- Select one test by node id.  A whole suite produces a trace nobody
  can read, and fixtures of other tests get mixed in.
- pytest captures standard output.  The trace of a **failing** test is
  shown under "Captured stdout call".  The trace of a **passing** test
  is thrown away unless you pass pytest's `-s` or pyftrace's `-o FILE`.
- Options before `-m pytest` are pyftrace's, options after it are
  pytest's.  `-x -q` keeps pytest's own output short.
- pytest itself is library code and is not traced.  The trace starts at
  the test function; fixtures and `conftest.py` functions defined in
  the project appear as their own top-level calls before it.
- To see only the code under test and not the test's own helpers:
  `-F src` or `-E tests`.
- The exit status is pytest's, so a failing test still exits 1.
- `-r -m pytest ...` gives the time and call count per project function
  for that test.

## unittest

    python -m pyftrace -a -m unittest tests.test_cart.CartTest.test_total

The trace is printed live, around unittest's own dots.  `setUp` and
`tearDown` appear as top-level calls next to the test method.

## Web frameworks (Django, Flask, FastAPI)

Do not trace a development server to understand one request: it does
not end, it may fork a reloader, and every request is mixed into one
trace.  Drive one request through the framework's test client instead,
in a test or a short script, and trace that:

    python -m pyftrace -a -m pytest tests/test_views.py::test_article_detail -q -s

By default the trace shows the project's middleware, views and helpers
in the order the framework called them, without the framework's own
frames.  To see how the framework got from one to the next, add `-v`
and keep it bounded:

    python -m pyftrace -v -p -f article_detail -d 6 -n 200 -m pytest ... -s

`examples/django_example.py` in the pyftrace repository is a complete
single-file Django application to try this on.

## Async code

Coroutines are traced like generators: one `Called`/`Returning` pair
per resumption (see `output.md`).  A coroutine that has not finished
returns `<Future pending>`; look for its last `Returning` line for the
real result.  Tasks run concurrently interleave in the trace, so filter
to one coroutine with `-f` when the order of the others does not
matter.

A coroutine that is created but never awaited never prints `Called`.
That is the usual reason an `async def` is missing from a trace.

## Threads and processes

Threads other than the main one are marked `[tid N]`, child processes
`[pid N]` (both `fork` and `spawn`, and `multiprocessing.Pool`
workers).  Lines of different threads interleave; each thread's
indentation is its own depth.

    python -m pyftrace -o /tmp/trace.txt script.py
    grep -F '[tid 68479205]' /tmp/trace.txt     # one thread
    grep -v -e '\[tid' -e '\[pid' /tmp/trace.txt  # the main thread only

`-n` limits the lines of all threads and processes together, and may
overrun by a line or two when several are printing at once.  `-r` adds
the calls made in child processes to the report.

Programs started with `subprocess` or `os.exec` are separate programs
and are not traced.  Trace them by running pyftrace on them directly.

## Programs that read input

Standard input goes to the program:

    echo 4 | python -m pyftrace script.py
    python -m pyftrace script.py < input.txt

A program that prompts and waits will hang under an agent exactly as it
would without pyftrace.  Give it its input.

## Programs that do not end

Servers, workers and watch loops never reach the end of the trace.
Write the trace to a file, let the program run for as long as the
behaviour takes to happen, and stop it:

    python -m pyftrace -o /tmp/trace.txt worker.py &
    PID=$!; sleep 5; kill $PID; wait $PID
    tail -40 /tmp/trace.txt

Use plain `kill`.  A shell script ignores `kill -INT` for a background
job, and the program would never stop.  The file is written line by
line, so it is complete up to the moment the program stopped, and can
be read while the program is still running.

For a program that hangs, the last lines of the file are the answer:
the last `Called` without a matching `Returning` is the function it is
stuck in.

## Programs that crash hard

Each trace line is flushed as it is written.  When the interpreter dies
of a segmentation fault or is killed, the last line of the trace is the
last call that started.

## Programs that profile or trace themselves

On Python 3.12 or later a program can run cProfile, coverage or a
debugger while it is traced.  On Python 3.8 to 3.11 pyftrace uses the
profiling hook of the interpreter, and a program that takes the hook
for itself (`cProfile`, `sys.setprofile`) and does not give it back
ends the trace at that point.

## Large or slow programs

Tracing adds work to every call.  The default trace skips library code
cheaply, so programs that spend their time inside NumPy, PyTorch or
Django are slowed down far less than programs that make millions of
calls in their own code.  `-v` removes that advantage.
If a run is too slow under pyftrace, narrow what is traced (`-F`, drop
`-v`) before reducing the input.
