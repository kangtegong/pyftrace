import sys
import os
import site
import sysconfig
from abc import ABC, abstractmethod
from .utils import find_import_end_line

class PyftraceBase(ABC):
    """
    Abstract base class defining the interface for tracers.
    """
    def __init__(self, verbose=False, show_path=False, report_mode=False, output_stream=sys.stdout, function_filter=None, function_exclude=None, trace_arguments=False):
        self.script_name = None
        self.script_dir = None
        self.report_mode = report_mode
        self.execution_report = {}
        self.call_stack = []
        self.tracer_script = os.path.abspath(__file__)
        self.tracer_dir = os.path.dirname(self.tracer_script)
        self.tracing_started = False
        self.verbose = verbose
        self.show_path = show_path
        self.output_stream = output_stream
        self.import_end_line = 0
        self.max_depth = None
        self.trace_arguments = trace_arguments

        # Get the standard library directory
        paths = sysconfig.get_paths()
        self.stdlib_dirs = self.normalize_dirs(
            [paths["stdlib"], paths["platstdlib"]])
        self.site_dirs = self.find_site_dirs()

        self.function_filter = function_filter
        self.filter_depth = 0
        self.function_exclude = function_exclude
        self.exclude_depth = 0

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

        self.tracing_started = False
        self.setup_tracing()

        try:
            run()
        finally:
            self.tracing_started = False
            self.cleanup_tracing()
            sys.path = old_sys_path
            sys.argv = old_sys_argv

    def run_python_script(self, script_path, script_args):
        if self.output_stream:
            print(f"Running script: {script_path}", file=self.output_stream)

        with open(script_path, "r") as file:
            code_object = compile(file.read(), script_path, 'exec')
        script_globals = {"__file__": script_path, "__name__": "__main__"}

        def run():
            sys.path.insert(0, self.script_dir)
            exec(code_object, script_globals)

        self.run_traced(script_path, [script_path] + script_args, run)

    def print_report(self, stream=None):
        stream = stream or self.output_stream or sys.stdout
        print("\nFunction Name\t| Total Execution Time\t| Call Count", file=stream)
        print("---------------------------------------------------------", file=stream)
        sorted_report = sorted(
            self.execution_report.items(), key=lambda item: item[1][1], reverse=True
        )
        for func_name, (_, total_time, call_count) in sorted_report:
            print(f"{func_name:<15}\t| {total_time:.6f} seconds\t| {call_count}", file=stream)

    def current_depth(self):
        return len(self.call_stack)

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

def get_tracer(verbose=False, show_path=False, report_mode=False, output_stream=sys.stdout, function_filter=None, function_exclude=None, trace_arguments=False):
    # Argument tracing requires access to frame locals, which is only available
    # in the setprofile-based tracer. Prefer it when trace_arguments is enabled.
    if trace_arguments:
        return PyftraceSetprofile(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)
    if sys.version_info >= (3, 12):
        return PyftraceMonitoring(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)
    else:
        return PyftraceSetprofile(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)

