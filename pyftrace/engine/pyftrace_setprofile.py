import sys
import os
import time
import sysconfig
from ..pyftrace_base import PyftraceBase
from ..utils import resolve_filename, get_line_number

class PyftraceSetprofile(PyftraceBase):
    """
    sys.setprofile based tracer
    """
    def setup_monitoring(self):
        sys.setprofile(self.profile_func)

    def cleanup_monitoring(self):
        sys.setprofile(None)

    def run_python_script(self, script_path, script_args):
        if self.output_stream:
            print(f"Running script: {script_path}", file=self.output_stream)

        self.script_name = os.path.abspath(script_path)
        self.script_dir = os.path.dirname(self.script_name)

        # For use import_end_line to start tracing after imports
        self.import_end_line = self.find_import_end_line(script_path)

        with open(script_path, "r") as file:
            script_code = file.read()
            code_object = compile(script_code, script_path, 'exec')

        old_sys_path = sys.path.copy()
        old_sys_argv = sys.argv.copy()
        sys.path.insert(0, self.script_dir)
        sys.argv = [script_path] + script_args

        self.tracing_started = False

        self.setup_monitoring()

        try:
            exec(code_object, {"__file__": script_path, "__name__": "__main__"})
        finally:
            self.cleanup_monitoring()
            sys.path = old_sys_path
            sys.argv = old_sys_argv

    def print_report(self):
        print("\nFunction Name\t| Total Execution Time\t| Call Count")
        print("---------------------------------------------------------")
        sorted_report = sorted(
            self.execution_report.items(), key=lambda item: item[1][1], reverse=True
        )
        for func_name, (_, total_time, call_count) in sorted_report:
            print(f"{func_name:<15}\t| {total_time:.6f} seconds\t| {call_count}")

    def profile_func(self, frame, event, arg):
        if event == "call":
            self.handle_call_event(frame, arg)
        elif event == "return":
            self.handle_return_event(frame, arg, is_c_return=False)
        elif event == "c_call":
            self.handle_call_event(frame, arg, is_c_call=True)
        elif event == "c_return":
            self.handle_return_event(frame, arg, is_c_return=True)
        elif event == "c_exception":
            pass
        else:
            pass

    def handle_call_event(self, frame, arg, is_c_call=False):
        code = frame.f_code if not is_c_call else None
        func_name = code.co_name if code else arg.__name__
        filename = resolve_filename(code, None) if code else resolve_filename(None, arg)
        if filename:
            filename = os.path.abspath(filename)

        if filename.startswith(self.tracer_dir):
            return

        # Start tracing when entering the script's code after imports
        if not self.tracing_started:
            if filename == self.script_name and frame.f_lineno > self.import_end_line:
                self.tracing_started = True
            else:
                return

        # After tracing has started, skip tracing the '<module>' function
        if func_name == '<module>':
            return

        # Exclude stdlib and frozen modules
        if self.is_stdlib_code(filename):
            return

        trace_this = False
        module_name = frame.f_globals.get('__name__', None) if frame.f_globals else None

        if (is_c_call or module_name == 'builtins') and self.verbose:
            caller_frame = frame.f_back
            caller_filename = resolve_filename(caller_frame.f_code, None) if caller_frame else None
            if caller_filename:
                caller_filename = os.path.abspath(caller_filename)
                if self.should_trace(caller_filename):
                    trace_this = True
        else:
            if self.should_trace(filename):
                trace_this = True
            elif self.verbose:
                if not self.is_stdlib_code(filename):
                    trace_this = True

        if trace_this:
            indent = "    " * self.current_depth()

            if not is_c_call and code:
                func_def_lineno = code.co_firstlineno
            else:
                func_def_lineno = ''

            caller_frame = frame.f_back
            call_lineno = ''
            call_filename = ''
            if caller_frame:
                call_lineno = get_line_number(caller_frame.f_code, caller_frame.f_lasti)
                call_filename = resolve_filename(caller_frame.f_code, None)
                if call_filename:
                    call_filename = os.path.abspath(call_filename)

            if self.show_path:
                if func_def_lineno:
                    func_location = f"{func_name}@{filename}:{func_def_lineno}"
                else:
                    func_location = f"{func_name}@{filename}"
                call_location = f"from {call_filename}:{call_lineno}"
            else:
                func_location = func_name
                call_location = f"from line {call_lineno}"

            if not self.report_mode and self.output_stream:
                print(f"{indent}Called {func_location} {call_location}", file=self.output_stream)

            # Store function name instead of frame
            self.call_stack.append(func_name)

            if self.report_mode:
                start_time = time.time()
                if func_name in self.execution_report:
                    _, total_time, call_count = self.execution_report[func_name]
                    self.execution_report[func_name] = (start_time, total_time, call_count + 1)
                else:
                    self.execution_report[func_name] = (start_time, 0, 1)

    def handle_return_event(self, frame, arg, is_c_return):
        if not self.tracing_started:
            return

        code = frame.f_code if not is_c_return else None
        func_name = code.co_name if code else arg.__name__
        filename = resolve_filename(code, None) if code else resolve_filename(None, arg)
        if filename:
            filename = os.path.abspath(filename)

        if filename.startswith(self.tracer_dir):
            return

        # Skip tracing '<module>'
        if func_name == '<module>':
            return

        # Exclude stdlib and frozen modules
        if self.is_stdlib_code(filename):
            return

        trace_this = False

        # Compare function names instead of frames
        if self.call_stack and self.call_stack[-1] == func_name:
            trace_this = True

        if trace_this:
            func_name = self.call_stack.pop()

            indent = "    " * self.current_depth()

            if self.show_path:
                file_info = f" @ {filename}" if filename else ""
            else:
                file_info = ""

            if not self.report_mode and self.output_stream:
                return_value = ''
                if not is_c_return:
                    return_value = f"-> {arg}"
                print(f"{indent}Returning {func_name}{return_value}{file_info}", file=self.output_stream)

            if self.report_mode and func_name in self.execution_report:
                start_time, total_time, call_count = self.execution_report[func_name]
                exec_time = time.time() - start_time
                self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)

