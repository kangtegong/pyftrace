import sys
import os
from .pyftrace_base import PyftraceBase
from .engine.pyftrace_monitoring import PyftraceMonitoring
from .engine.pyftrace_setprofile import PyftraceSetprofile

class Pyftrace(PyftraceBase):
    def __init__(self, verbose=False, show_path=False, report_mode=False, output_stream=sys.stdout):
        super().__init__(verbose, show_path, report_mode, output_stream)
        if sys.version_info >= (3, 12):
            self.impl = PyftraceMonitoring(verbose, show_path, report_mode, output_stream)
            # self.impl = PyftraceSetprofile(verbose, show_path, report_mode, output_stream)
        else:
            self.impl = PyftraceSetprofile(verbose, show_path, report_mode, output_stream)

    def setup_monitoring(self):
        self.impl.setup_monitoring()

    def cleanup_monitoring(self):
        self.impl.cleanup_monitoring()

    def run_python_script(self, script_path, script_args):
        self.impl.run_python_script(script_path, script_args)

    def print_report(self):
        self.impl.print_report()

    def __getattr__(self, name):
        return getattr(self.impl, name)

