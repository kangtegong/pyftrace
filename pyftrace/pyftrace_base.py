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

        # Get the standard library directory
        self.stdlib_dir = os.path.abspath(sysconfig.get_paths()["stdlib"])

    @abstractmethod
    def setup_monitoring(self):
        pass

    @abstractmethod
    def cleanup_monitoring(self):
        pass

    @abstractmethod
    def run_python_script(self, script_path, script_args):
        pass

    @abstractmethod
    def print_report(self):
        pass

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
        abs_file_name = os.path.abspath(file_name)
        return abs_file_name.startswith(self.stdlib_dir)

    def find_import_end_line(self, script_path):
        """
        Finds the last line number of import statements in the script.
        """
        import_line_numbers = []
        with open(script_path, 'r') as f:
            for lineno, line in enumerate(f, 1):
                stripped_line = line.strip()
                if stripped_line.startswith('import ') or stripped_line.startswith('from '):
                    import_line_numbers.append(lineno)
        if import_line_numbers:
            return max(import_line_numbers)
        else:
            return 0

