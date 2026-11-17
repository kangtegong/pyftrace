import sys
import os
import time
import weakref
import sysconfig
from ..tracer import PyftraceBase
from ..utils import resolve_filename, get_line_number, callable_name
from ..utils import format_arguments, is_function_code

class PyftraceMonitoring(PyftraceBase):
    """
    sys.monitoring based tracer.
    """

    def __init__(self, verbose, show_path, report_mode, output_stream, function_filter=None, function_exclude=None, trace_arguments=False):
        super().__init__(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)

    def setup_tracing(self):
        self.tool_id = 1
        sys.monitoring.use_tool_id(self.tool_id, "pyftrace")
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_START, self.monitor_py_start)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_RESUME, self.monitor_py_start)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_YIELD, self.monitor_py_return)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.CALL, self.monitor_call)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_RETURN, self.monitor_py_return)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.C_RETURN, self.monitor_c_return)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_UNWIND, self.monitor_py_unwind)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.C_RAISE, self.monitor_c_raise)
        sys.monitoring.set_events(
            self.tool_id,
            sys.monitoring.events.PY_START |
            sys.monitoring.events.PY_RESUME |
            sys.monitoring.events.PY_YIELD |
            sys.monitoring.events.CALL |
            sys.monitoring.events.PY_RETURN |
            sys.monitoring.events.PY_UNWIND |
            sys.monitoring.events.C_RETURN |
            sys.monitoring.events.C_RAISE
        )

    def cleanup_tracing(self):
        sys.monitoring.free_tool_id(self.tool_id)
        self.output_stream = None

    # A generator or coroutine leaves the call stack while it is
    # suspended: PY_YIELD is handled like a return and PY_RESUME like a
    # call, as a profile function sees them.

    def monitor_py_start(self, code, instruction_offset):
        # The callback is called from the frame of the function
        self.handle_py_start_event(code, sys._getframe(1))

    def monitor_call(self, code, instruction_offset, callable_obj, arg0):
        self.handle_call_event(code, instruction_offset, callable_obj)

    def monitor_py_return(self, code, instruction_offset, retval):
        self.handle_py_return_event(code, instruction_offset, retval)

    def monitor_py_unwind(self, code, instruction_offset, exception):
        self.handle_py_return_event(code, instruction_offset, None, exception)

    def monitor_c_return(self, code, instruction_offset, callable_obj, arg0):
        self.handle_c_return_event(code, instruction_offset, callable_obj)

    def monitor_c_raise(self, code, instruction_offset, callable_obj, arg0):
        self.handle_c_return_event(code, instruction_offset, callable_obj,
                                   raised=True)

    def handle_py_start_event(self, code, frame):
        """
        A Python function starts running.  Unlike CALL, this is also
        reported when the function is called from C code, e.g. by map().
        """
        func_name = code.co_name
        def_filename = os.path.abspath(code.co_filename)

        if not self.tracing_started:
            # Start tracing when the script's top-level code is entered
            if func_name == '<module>' and def_filename == self.script_name:
                self.tracing_started = True
            return

        if not is_function_code(code) or self.is_tracer_code(def_filename):
            return

        caller = frame.f_back
        call_lineno = 0
        call_filename = ''
        if caller:
            call_lineno = caller.f_lineno
            call_filename = resolve_filename(caller.f_code, None)
        if call_filename:
            call_filename = os.path.abspath(call_filename)

        trace_this = False
        if not self.is_stdlib_code(def_filename):
            trace_this = self.should_trace(def_filename) or self.verbose
        trace_this = trace_this and self.file_selected(def_filename)

        arguments = ""
        if self.trace_arguments and trace_this:
            arguments = format_arguments(frame)

        def_location = f"{def_filename}:{code.co_firstlineno}"
        self.trace_call(func_name, False, trace_this, def_location,
                        call_filename, call_lineno, arguments)

    def handle_call_event(self, code, instruction_offset, callable_obj):
        if not self.tracing_started:
            return

        if isinstance(callable_obj, weakref.ReferenceType):
            callable_obj = callable_obj()

        # Python functions are traced when they start, see above
        if hasattr(callable_obj, '__code__'):
            return

        call_lineno = get_line_number(code, instruction_offset)
        call_filename = resolve_filename(code, None)
        if call_filename:
            call_filename = os.path.abspath(call_filename)

        func_name = callable_name(callable_obj)
        module_name = getattr(callable_obj, '__module__', None)
        is_builtin = module_name in (None, 'builtins')

        def_filename = resolve_filename(None, callable_obj)
        if def_filename:
            def_filename = os.path.abspath(def_filename)

        trace_this = False
        if is_builtin:
            # Only trace built-in functions for `verbose`
            if self.verbose and self.should_trace(call_filename):
                trace_this = True
        else:
            if self.verbose and self.should_trace(def_filename):
                trace_this = True

        # A function without a source file belongs to the file calling it
        trace_this = trace_this and self.file_selected(call_filename)

        if is_builtin or not def_filename:
            def_location = module_name or '<builtin>'
        else:
            def_location = def_filename
        self.trace_call(func_name, is_builtin, trace_this, def_location,
                        call_filename, call_lineno)

    def trace_call(self, func_name, is_builtin, trace_this, def_location,
                   call_filename, call_lineno, arguments=""):
        if self.function_exclude and func_name in self.function_exclude:
            self.exclude_depth += 1
        if self.exclude_depth > 0:
            return

        if self.function_filter:
            if func_name in self.function_filter and trace_this:
                self.filter_depth += 1
            if self.filter_depth == 0 or not trace_this:
                return

        if trace_this and not self.is_tracer_code(call_filename):
            self.call_stack.append((func_name, is_builtin))
            self.emit_call(func_name, def_location, call_filename, call_lineno,
                           arguments)

            if self.report_mode:
                start_time = time.time()
                if func_name in self.execution_report:
                    _, total_time, call_count = self.execution_report[func_name]
                    self.execution_report[func_name] = (start_time, total_time, call_count + 1)
                else:
                    self.execution_report[func_name] = (start_time, 0, 1)

    def handle_py_return_event(self, code, instruction_offset, retval, exception=None):
        if not self.tracing_started:
            return

        filename = resolve_filename(code, None)
        if filename:
            filename = os.path.abspath(filename)
        func_name = code.co_name if code else "<unknown>"

        # Module and class bodies are not traced
        if not code or not is_function_code(code):
            return

        if self.exclude_depth > 0:
            if self.function_exclude and func_name in self.function_exclude:
                self.exclude_depth -= 1
            return

        trace_this = self.should_trace(filename) or self.verbose
        trace_this = trace_this and self.file_selected(filename)

        if self.function_filter:
            if self.filter_depth == 0:
                return
            if func_name in self.function_filter and trace_this:
                self.filter_depth -= 1

        if trace_this and not self.is_tracer_code(filename):
            if self.call_stack and self.call_stack[-1][0] == func_name:
                self.emit_exit(func_name, filename, value=retval,
                               exception=exception)

                if self.report_mode and func_name in self.execution_report:
                    start_time, total_time, call_count = self.execution_report[func_name]
                    exec_time = time.time() - start_time
                    self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)

                self.call_stack.pop()

    def handle_c_return_event(self, code, instruction_offset, callable_obj, raised=False):
        if not self.tracing_started:
            return

        func_name = callable_name(callable_obj)
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

        trace_this = trace_this and self.file_selected(filename)

        if self.exclude_depth > 0:
            if self.function_exclude and func_name in self.function_exclude:
                self.exclude_depth -= 1
            return

        if not self.is_tracer_code(filename) and trace_this:
            if self.call_stack and self.call_stack[-1][0] == func_name:
                self.emit_exit(func_name, filename, raised=raised)

                if self.report_mode and func_name in self.execution_report:
                    start_time, total_time, call_count = self.execution_report[func_name]
                    exec_time = time.time() - start_time
                    self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)

                self.call_stack.pop()

