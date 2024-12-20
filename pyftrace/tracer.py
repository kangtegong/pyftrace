import sys
import os
import sysconfig
from abc import ABC, abstractmethod
from .utils import get_site_packages_modules, resolve_filename, get_line_number

class PyftraceBase(ABC):
    """
    Abstract base class defining the interface for tracers.
    """
    def __init__(self, verbose=False, show_path=False, report_mode=False, output_stream=sys.stdout):
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

        # Get the standard library directory
        self.stdlib_dir = os.path.abspath(sysconfig.get_paths()["stdlib"])

    @abstractmethod
    def setup_tracing(self):
        pass

    @abstractmethod
    def cleanup_tracing(self):
        pass

    @abstractmethod
    def run_python_script(self, script_path, script_args):
        pass

    def print_report(self):
        print("\nFunction Name\t| Total Execution Time\t| Call Count")
        print("---------------------------------------------------------")
        sorted_report = sorted(
            self.execution_report.items(), key=lambda item: item[1][1], reverse=True
        )
        for func_name, (_, total_time, call_count) in sorted_report:
            print(f"{func_name:<15}\t| {total_time:.6f} seconds\t| {call_count}")

    def current_depth(self):
        return len(self.call_stack)

    def should_trace(self, file_name):
        if not file_name:
            return False
        abs_file_name = os.path.abspath(file_name)
        if self.is_tracer_code(abs_file_name):
            return False
        if self.is_stdlib_code(abs_file_name):
            return False
        return True

    def is_tracer_code(self, file_name):
        if not file_name:
            return False
        abs_file_name = os.path.abspath(file_name)
        return abs_file_name.startswith(self.tracer_dir)

    def is_stdlib_code(self, file_name):
        if not file_name:
            return False
        if file_name.startswith('<frozen'):
            return True  # Exclude frozen modules
        abs_file_name = os.path.normcase(os.path.abspath(file_name))
        stdlib_dir_norm = os.path.normcase(self.stdlib_dir)
        return abs_file_name.startswith(stdlib_dir_norm)

# Import engine modules AFTER defining PyftraceBase (avoid circular imports)
from .engine.pyftrace_monitoring import PyftraceMonitoring
from .engine.pyftrace_setprofile import PyftraceSetprofile

def get_tracer(verbose=False, show_path=False, report_mode=False, output_stream=sys.stdout):
    if sys.version_info >= (3, 12):
        return PyftraceMonitoring(verbose, show_path, report_mode, output_stream)
    else:
        return PyftraceSetprofile(verbose, show_path, report_mode, output_stream)

