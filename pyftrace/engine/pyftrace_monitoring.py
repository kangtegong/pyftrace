import sys
import os
import time
import weakref
import sysconfig
from ..pyftrace_base import PyftraceBase
from ..utils import get_site_packages_modules, resolve_filename, get_line_number

class PyftraceMonitoring(PyftraceBase):
    """
    sys.monitoring based tracer.
    """
    def setup_monitoring(self):
        self.tool_id = 1
        sys.monitoring.use_tool_id(self.tool_id, "pyftrace")
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.CALL, self.monitor_call)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_RETURN, self.monitor_py_return)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.C_RETURN, self.monitor_c_return)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.C_RAISE, self.monitor_c_raise)
        sys.monitoring.set_events(
            self.tool_id,
            sys.monitoring.events.CALL |
            sys.monitoring.events.PY_RETURN |
            sys.monitoring.events.C_RETURN |
            sys.monitoring.events.C_RAISE
        )

    def cleanup_monitoring(self):
        sys.monitoring.free_tool_id(self.tool_id)
        self.output_stream = None

    def run_python_script(self, script_path, script_args):
        if self.output_stream:
            print(f"Running script: {script_path}", file=self.output_stream)

        self.script_name = os.path.abspath(script_path)
        self.script_dir = os.path.dirname(self.script_name)

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

    def monitor_call(self, code, instruction_offset, callable_obj, arg0):
        self.handle_call_event(code, instruction_offset, callable_obj)

    def monitor_py_return(self, code, instruction_offset, retval):
        self.handle_py_return_event(code, instruction_offset, retval)

    def monitor_c_return(self, code, instruction_offset, callable_obj, arg0):
        self.handle_c_return_event(code, instruction_offset, callable_obj)

    def monitor_c_raise(self, code, instruction_offset, callable_obj, arg0):
        pass  # Placeholder for handling C_RAISE events

    def handle_call_event(self, code, instruction_offset, callable_obj):
        if not self.tracing_started:
            # Start tracing when  enter script's '<module>' code
            if code and os.path.abspath(code.co_filename) == os.path.abspath(self.script_name) and code.co_name == '<module>':
                self.tracing_started = True
            else:
                return

        call_lineno = get_line_number(code, instruction_offset)
        call_filename = resolve_filename(code, None)
        if call_filename:
            call_filename = os.path.abspath(call_filename)

        if isinstance(callable_obj, weakref.ReferenceType):
            callable_obj = callable_obj()

        func_name = getattr(callable_obj, '__name__', str(callable_obj))
        module_name = getattr(callable_obj, '__module__', None)
        is_builtin = module_name in (None, 'builtins')

        # Exclude stdlib and frozen modules
        def_filename = ''
        func_def_lineno = ''
        trace_this = False

        if hasattr(callable_obj, '__code__'):
            func_def_lineno = callable_obj.__code__.co_firstlineno
            def_filename = os.path.abspath(callable_obj.__code__.co_filename)
            if not self.is_stdlib_code(def_filename):
                trace_this = self.should_trace(def_filename) or self.verbose
            else:
                trace_this = False  # Exclude stdlib
        else:
            def_filename = resolve_filename(None, callable_obj)
            if def_filename:
                def_filename = os.path.abspath(def_filename)
            if is_builtin:
                # Only trace built-in functions for `verbose`
                if self.verbose and self.should_trace(call_filename):
                    trace_this = True
                else:
                    trace_this = False
            else:
                if self.verbose and self.should_trace(def_filename):
                    trace_this = True

        if trace_this and not self.is_tracer_code(call_filename):
            indent = "    " * self.current_depth()
            if self.show_path:
                if is_builtin or not def_filename:
                    func_location = f"{func_name}@{module_name or '<builtin>'}"
                else:
                    func_location = f"{func_name}@{def_filename}:{func_def_lineno}"
                call_location = f"from {call_filename}:{call_lineno}"
            else:
                func_location = func_name
                call_location = f"from line {call_lineno}"
            if not self.report_mode and self.output_stream:
                print(f"{indent}Called {func_location} {call_location}", file=self.output_stream)
            self.call_stack.append((func_name, is_builtin))
            if self.report_mode:
                start_time = time.time()
                if func_name in self.execution_report:
                    _, total_time, call_count = self.execution_report[func_name]
                    self.execution_report[func_name] = (start_time, total_time, call_count + 1)
                else:
                    self.execution_report[func_name] = (start_time, 0, 1)

    def handle_py_return_event(self, code, instruction_offset, retval):
        if not self.tracing_started:
            return

        filename = resolve_filename(code, None)
        if filename:
            filename = os.path.abspath(filename)
        func_name = code.co_name if code else "<unknown>"

        # Skip tracing the '<module>' function's return event
        if func_name == '<module>':
            return

        trace_this = self.should_trace(filename) or self.verbose

        if trace_this and not self.is_tracer_code(filename):
            if self.call_stack:
                stack_func_name, _ = self.call_stack[-1]
            else:
                stack_func_name = "<unknown>"

            indent = "    " * (self.current_depth() - 1)

            if self.show_path:
                file_info = f" @ {filename}" if filename else ""
            else:
                file_info = ""

            if stack_func_name == func_name:
                if not self.report_mode and self.output_stream:
                    print(f"{indent}Returning {func_name}-> {retval}{file_info}", file=self.output_stream)

                if self.report_mode and func_name in self.execution_report:
                    start_time, total_time, call_count = self.execution_report[func_name]
                    exec_time = time.time() - start_time
                    self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)

                if self.call_stack and self.call_stack[-1][0] == func_name:
                    self.call_stack.pop()

    def handle_c_return_event(self, code, instruction_offset, callable_obj):
        if not self.tracing_started:
            return

        func_name = getattr(callable_obj, '__name__', str(callable_obj))
        module_name = getattr(callable_obj, '__module__', None)
        is_builtin = module_name in (None, 'builtins')
        filename = resolve_filename(code, callable_obj)
        if filename:
            filename = os.path.abspath(filename)

        # Exclude stdlib and frozen modules
        if self.is_stdlib_code(filename):
            return

        trace_this = False
        if is_builtin:
            # Only trace built-in functions if verbose and called from script
            if self.verbose and self.call_stack:
                # Check if the caller is from script
                caller_filename = filename
                if caller_filename and self.should_trace(caller_filename):
                    trace_this = True
        else:
            if self.verbose and self.should_trace(filename):
                trace_this = True

        if trace_this and not self.is_tracer_code(filename):
            if self.call_stack:
                stack_func_name, _ = self.call_stack[-1]
            else:
                stack_func_name = "<unknown>"

            indent = "    " * (self.current_depth() - 1)

            if self.show_path:
                file_info = f" @ {filename}" if filename else ""
            else:
                file_info = ""

            if stack_func_name == func_name:
                if not self.report_mode and self.output_stream:
                    print(f"{indent}Returning {func_name}{file_info}", file=self.output_stream)
                if self.report_mode and func_name in self.execution_report:
                    start_time, total_time, call_count = self.execution_report[func_name]
                    exec_time = time.time() - start_time
                    self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)
                if self.call_stack and self.call_stack[-1][0] == func_name:
                    self.call_stack.pop()

