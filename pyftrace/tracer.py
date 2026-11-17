import sys
import os
import json
import runpy
import site
import sysconfig
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from .utils import find_import_end_line, find_module_file
from .utils import format_exception, safe_str
from .utils import path_matches
from .output import Collapser, LineCounter, format_text
from . import multiproc

# Marks a function exit that has no value to show
NO_VALUE = object()

class ThreadState:
    """
    What the tracer has to know about each thread on its own.
    """
    __slots__ = ("call_stack", "filter_depth", "exclude_depth", "collapser",
                 "tid", "muted", "start_times", "active_calls")

    def __init__(self):
        self.call_stack = []
        self.filter_depth = 0
        self.exclude_depth = 0
        self.collapser = None
        # Shown with every event of the thread; None for the main thread
        self.tid = None
        # Set once the thread has nothing more of the program to run
        self.muted = False
        # For --report: when each call on the stack started, and how many
        # calls of each function are on it
        self.start_times = []
        self.active_calls = {}

class PyftraceBase(ABC):
    """
    Abstract base class defining the interface for tracers.
    """
    def __init__(self, verbose=False, show_path=False, report_mode=False, output_stream=sys.stdout, function_filter=None, function_exclude=None, trace_arguments=False):
        self.script_name = None
        self.script_dir = None
        self.report_mode = report_mode
        self.execution_report = {}
        self.thread_states = threading.local()
        self.main_thread = threading.get_ident()
        self.output_lock = threading.Lock()
        self.collapsers = []
        # Shown with every event of a child process; None in the process
        # that pyftrace was started in
        self.pid = None
        self.fork_hooked = False
        # Where the trace goes if not to stdout; a spawned process has
        # to open the file itself
        self.output_path = None
        self.owns_output = False
        # Where child processes leave their part of the --report
        self.report_dir = None
        self.tracing_active = False
        self.tracer_script = os.path.abspath(__file__)
        self.tracer_dir = os.path.dirname(self.tracer_script)
        self.tracing_started = False
        self.verbose = verbose
        self.show_path = show_path
        self.output_stream = output_stream
        self.import_end_line = 0
        self.max_depth = None
        self.max_lines = None
        # Turns a trace event into a line of output, see output.py
        self.format = format_text
        # Fold repeated calls, see Collapser
        self.collapse = False
        # Counts the lines of all processes; needed for --max-lines only
        self.line_counter = None
        self.trace_arguments = trace_arguments

        # Get the standard library directory
        paths = sysconfig.get_paths()
        self.stdlib_dirs = self.normalize_dirs(
            [paths["stdlib"], paths["platstdlib"]])
        self.site_dirs = self.find_site_dirs()

        # Sets of function names given with -f and -e
        self.function_filter = frozenset(function_filter or ())
        self.function_exclude = frozenset(function_exclude or ())

        # Normalized paths given with -F and -E
        self.file_filter = ()
        self.file_exclude = ()

    @property
    def thread_state(self):
        try:
            return self.thread_states.state
        except AttributeError:
            pass
        state = self.thread_states.state = ThreadState()
        if threading.get_ident() != self.main_thread:
            state.tid = threading.get_native_id()
        if self.collapse:
            state.collapser = Collapser(self.write_event)
            with self.output_lock:
                self.collapsers.append(state.collapser)
        return state

    # The engines keep their bookkeeping in these.  Each thread has its
    # own call stack, so each thread gets its own copy.
    @property
    def call_stack(self):
        return self.thread_state.call_stack

    @property
    def filter_depth(self):
        return self.thread_state.filter_depth

    @filter_depth.setter
    def filter_depth(self, depth):
        self.thread_state.filter_depth = depth

    @property
    def exclude_depth(self):
        return self.thread_state.exclude_depth

    @exclude_depth.setter
    def exclude_depth(self, depth):
        self.thread_state.exclude_depth = depth

    @abstractmethod
    def setup_tracing(self):
        pass

    @abstractmethod
    def cleanup_tracing(self):
        pass

    def run_traced(self, target_path, argv, run):
        """
        Call run() with tracing enabled.  target_path is the file whose
        top-level code starts the trace.
        """
        self.script_name = os.path.abspath(target_path)
        self.script_dir = os.path.dirname(self.script_name)

        # The setprofile engine starts tracing after the imports
        self.import_end_line = find_import_end_line(target_path)

        old_sys_path = sys.path.copy()
        old_sys_argv = sys.argv.copy()
        sys.argv = argv

        # The thread running the target is the one shown without a tid
        self.main_thread = threading.get_ident()
        self.thread_states = threading.local()

        self.follow_forks()
        multiproc.follow(self)
        if self.report_mode:
            self.report_dir = tempfile.mkdtemp(prefix="pyftrace-report-")
        if self.max_lines is not None:
            self.line_counter = LineCounter()

        self.tracing_started = False
        self.setup_tracing()
        self.tracing_active = True

        try:
            try:
                run()
            finally:
                self.wait_for_threads()
        finally:
            self.tracing_started = False
            for collapser in self.collapsers:
                collapser.finish()
            if self.line_counter and self.pid is None:
                self.line_counter.remove()
            self.cleanup_tracing()
            sys.path = old_sys_path
            sys.argv = old_sys_argv

    def follow_forks(self):
        """
        A forked child keeps tracing with a copy of this tracer.  Have
        it start from a clean state under its own pid.
        """
        if self.fork_hooked or not hasattr(os, "register_at_fork"):
            return
        os.register_at_fork(after_in_child=self.enter_child)
        self.fork_hooked = True

    def enter_child(self):
        self.pid = os.getpid()
        # The copy of the parent's report stays with the parent
        self.execution_report = {}
        # The forking thread is the only one left and is now the main one
        self.main_thread = threading.get_ident()
        self.thread_states = threading.local()
        # Another thread may have held the lock when the process forked
        self.output_lock = threading.Lock()
        self.collapsers = []

    def child_config(self):
        """
        Everything a spawned process needs to build a tracer like this.
        """
        return {
            "arguments": {
                "verbose": self.verbose,
                "show_path": self.show_path,
                "report_mode": self.report_mode,
                "function_filter": sorted(self.function_filter),
                "function_exclude": sorted(self.function_exclude),
                "trace_arguments": self.trace_arguments,
            },
            "attributes": {
                "max_depth": self.max_depth,
                "max_lines": self.max_lines,
                "collapse": self.collapse,
                "format": self.format,
                "file_filter": self.file_filter,
                "file_exclude": self.file_exclude,
                "output_path": self.output_path,
                "report_dir": self.report_dir,
                "line_counter_path": (self.line_counter.path
                                      if self.line_counter else None),
                "script_name": self.script_name,
                "script_dir": self.script_dir,
                "import_end_line": self.import_end_line,
            },
        }

    def start_child(self):
        """
        Called in a child process right before it runs its target.
        """
        if self.pid != os.getpid():
            self.enter_child()
        if not self.tracing_active:
            # A spawned process: nothing was inherited, start from scratch
            self.follow_forks()
            self.setup_tracing()
            self.tracing_active = True
        self.tracing_started = True

    def finish_child(self):
        self.tracing_started = False
        self.save_child_report()
        for collapser in self.collapsers:
            collapser.finish()
        if self.output_stream:
            self.output_stream.flush()
        if self.owns_output:
            # Opened by tracer_from_config().  Left open, the file would
            # only be closed while the interpreter is being torn down.
            self.output_stream.close()
        self.output_stream = None
        self.cleanup_tracing()
        self.tracing_active = False

    @staticmethod
    def wait_for_threads():
        """
        Wait for the threads the interpreter would wait for at exit.
        They are part of the program and tracing must not end before
        they do.
        """
        current = threading.current_thread()
        while True:
            threads = [thread for thread in threading.enumerate()
                       if thread is not current and not thread.daemon]
            if not threads:
                return
            for thread in threads:
                thread.join()

    def run_python_script(self, script_path, script_args):
        self.emit_start({"event": "start", "script": script_path})

        # Run the script as the real __main__ module, like python does:
        # pickle, and with it multiprocessing, looks its functions up there.
        def run():
            sys.path.insert(0, self.script_dir)
            runpy.run_path(script_path, run_name="__main__")

        self.run_traced(script_path, [script_path] + script_args, run)

    def run_python_module(self, module_name, module_args):
        module_path = find_module_file(module_name)
        if module_path is None:
            raise ImportError(f"No module named {module_name}")

        self.emit_start({"event": "start", "module": module_name})

        def run():
            runpy.run_module(module_name, run_name="__main__", alter_sys=True)

        self.run_traced(module_path, [module_path] + module_args, run)

    def emit_start(self, event):
        # The header is not part of the trace: --max-lines does not count it
        if self.output_stream:
            print(self.format(event), file=self.output_stream)

    def report_call(self, func_name):
        if not self.report_mode:
            return
        state = self.thread_state
        state.start_times.append(time.time())
        state.active_calls[func_name] = state.active_calls.get(func_name, 0) + 1

    def report_return(self, func_name):
        state = self.thread_state
        if not self.report_mode or not state.start_times:
            return
        exec_time = time.time() - state.start_times.pop()
        state.active_calls[func_name] -= 1
        # A recursive call runs within the time of the outermost one
        if state.active_calls[func_name] > 0:
            exec_time = 0

        with self.output_lock:
            total_time, call_count = self.execution_report.get(func_name, (0, 0))
            self.execution_report[func_name] = (total_time + exec_time, call_count + 1)

        # A child process may be killed without warning, as the workers
        # of a multiprocessing pool are.  Do not wait for its end.
        if self.pid is not None and not state.start_times:
            self.save_child_report()

    def save_child_report(self):
        """
        Leave the report of a child process where the process that
        prints the report will find it.
        """
        if not self.report_dir or not self.execution_report:
            return
        path = os.path.join(self.report_dir, f"{os.getpid()}.json")
        # The process can be killed at any point.  Replace the file in
        # one step so that a complete report is there at all times.
        try:
            with open(path + ".tmp", "w") as file:
                json.dump(self.execution_report, file)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def collect_child_reports(self):
        if not self.report_dir:
            return
        for name in os.listdir(self.report_dir):
            path = os.path.join(self.report_dir, name)
            child_report = {}
            if name.endswith(".json"):
                with open(path) as file:
                    child_report = json.load(file)
            os.remove(path)
            for func_name, (child_time, child_count) in child_report.items():
                total_time, call_count = self.execution_report.get(func_name, (0, 0))
                self.execution_report[func_name] = (total_time + child_time, call_count + child_count)
        os.rmdir(self.report_dir)
        self.report_dir = None

    def print_report(self, stream=None):
        stream = stream or self.output_stream or sys.stdout
        self.collect_child_reports()
        if self.format is format_text:
            print("\nFunction Name\t| Total Execution Time\t| Call Count", file=stream)
            print("---------------------------------------------------------", file=stream)
        sorted_report = sorted(
            self.execution_report.items(), key=lambda item: item[1][0], reverse=True
        )
        for func_name, (total_time, call_count) in sorted_report:
            event = {"event": "report", "function": func_name,
                     "seconds": total_time, "calls": call_count}
            print(self.format(event), file=stream)

    def current_depth(self):
        return len(self.call_stack)

    def should_emit(self):
        """
        True if a trace line at the current depth is to be printed.
        Check this before formatting the line.
        """
        if self.report_mode or not self.output_stream:
            return False
        if self.is_truncated():
            return False
        return self.max_depth is None or self.current_depth() <= self.max_depth

    def is_truncated(self):
        if self.line_counter is None:
            return False
        return self.line_counter.value > self.max_lines

    def emit_call(self, func_name, def_location, call_file, call_line,
                  arguments=""):
        if not self.should_emit():
            return

        event = {"event": "call", "depth": self.current_depth(),
                 "function": func_name, "line": call_line}
        if self.show_path and def_location:
            event["defined_at"] = def_location
        if self.show_path and call_file and call_line:
            event["caller_file"] = call_file
        if arguments:
            event["args"] = arguments

        self.emit(event)

    def emit_exit(self, func_name, file_name, value=NO_VALUE, exception=None,
                  raised=False):
        if not self.should_emit():
            return

        event = {"event": "return", "depth": self.current_depth(),
                 "function": func_name}
        if exception is not None or raised:
            event["event"] = "raise"
        if exception is not None:
            event["exception"] = format_exception(exception)
        elif not raised and value is not NO_VALUE:
            event["value"] = safe_str(value)
        if self.show_path and file_name:
            event["file"] = file_name

        self.emit(event)

    def emit(self, event):
        state = self.thread_state
        if self.pid is not None:
            event["pid"] = self.pid
        if state.tid is not None:
            event["tid"] = state.tid
        if state.collapser:
            state.collapser.feed(event)
        else:
            self.write_event(event)

    def write_event(self, event):
        # Threads share the line count and must not mix their lines
        with self.output_lock:
            if self.is_truncated():
                return
            if self.line_counter:
                self.line_counter.increment()
            if self.is_truncated():
                event = {"event": "truncated", "max_lines": self.max_lines}
            self.output_stream.write(self.format(event) + "\n")
            # A trace is read to find out why a program died, and a
            # program that dies does not flush its buffers.
            self.output_stream.flush()

    def should_trace(self, file_name):
        if not file_name:
            return False
        if self.is_pseudo_file(file_name):
            return False
        abs_file_name = os.path.abspath(file_name)
        if self.is_tracer_code(abs_file_name):
            return False
        if self.is_stdlib_code(abs_file_name):
            return False
        if not self.verbose and self.is_site_code(abs_file_name):
            return False
        return True

    def file_selected(self, file_name):
        """
        Apply -F and -E to the file a function belongs to.
        """
        if not self.file_filter and not self.file_exclude:
            return True
        if not file_name:
            return not self.file_filter
        path = os.path.normcase(os.path.abspath(file_name))
        if path_matches(path, self.file_exclude):
            return False
        return not self.file_filter or path_matches(path, self.file_filter)

    @staticmethod
    def is_pseudo_file(file_name):
        """
        True for code without a source file, such as '<string>' or
        '<frozen posixpath>'.  Callers may pass the name through
        os.path.abspath() first, so only look at the last component.
        """
        return os.path.basename(file_name).startswith('<')

    def is_tracer_code(self, file_name):
        if not file_name:
            return False
        abs_file_name = os.path.abspath(file_name)
        return abs_file_name.startswith(self.tracer_dir)

    @staticmethod
    def find_site_dirs():
        paths = sysconfig.get_paths()
        dirs = [paths["purelib"], paths["platlib"]]
        if hasattr(site, "getsitepackages"):
            dirs += site.getsitepackages()
        if hasattr(site, "getusersitepackages"):
            dirs.append(site.getusersitepackages())
        return PyftraceBase.normalize_dirs(dirs)

    @staticmethod
    def normalize_dirs(dirs):
        """
        Return dirs as a tuple for str.startswith().  Code objects may
        record the symlinked or the resolved path, so keep both.
        """
        result = set()
        for d in dirs:
            result.add(os.path.normcase(os.path.abspath(d)))
            result.add(os.path.normcase(os.path.realpath(d)))
        return tuple(os.path.join(d, '') for d in result)

    def is_site_code(self, file_name):
        if not file_name:
            return False
        abs_file_name = os.path.normcase(os.path.abspath(file_name))
        return abs_file_name.startswith(self.site_dirs)

    def is_stdlib_code(self, file_name):
        if not file_name:
            return False
        if os.path.basename(file_name).startswith('<frozen'):
            return True  # Exclude frozen modules
        abs_file_name = os.path.normcase(os.path.abspath(file_name))
        return abs_file_name.startswith(self.stdlib_dirs)

# Import engine modules AFTER defining PyftraceBase (avoid circular imports)
from .engine.pyftrace_monitoring import PyftraceMonitoring
from .engine.pyftrace_setprofile import PyftraceSetprofile

def tracer_from_config(config):
    """
    Build the tracer of a spawned process from child_config().
    """
    attributes = config["attributes"]
    output_stream = sys.stdout
    if attributes["output_path"]:
        output_stream = open(attributes["output_path"], "a", buffering=1,
                             encoding="utf-8")

    tracer = get_tracer(output_stream=output_stream, **config["arguments"])
    counter_path = attributes.pop("line_counter_path")
    for name, value in attributes.items():
        setattr(tracer, name, value)
    if counter_path:
        tracer.line_counter = LineCounter(counter_path)
    tracer.pid = os.getpid()
    tracer.owns_output = bool(attributes["output_path"])
    return tracer

def get_tracer(verbose=False, show_path=False, report_mode=False, output_stream=sys.stdout, function_filter=None, function_exclude=None, trace_arguments=False):
    if sys.version_info >= (3, 12):
        return PyftraceMonitoring(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)
    else:
        return PyftraceSetprofile(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)

