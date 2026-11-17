import sys
import os
import time
import sysconfig
import threading
from ..tracer import PyftraceBase
from ..utils import resolve_filename, format_arguments, callable_name
from ..utils import is_unwinding

class PyftraceSetprofile(PyftraceBase):
    """
    sys.setprofile based tracer
    """

    def __init__(self, verbose, show_path, report_mode, output_stream, function_filter=None, function_exclude=None, trace_arguments=False):
        super().__init__(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)

    def setup_tracing(self):
        # sys.setprofile() is per thread: hook the threads started later too
        self.stopped = False
        threading.setprofile(self.profile_func)
        sys.setprofile(self.profile_func)

    def cleanup_tracing(self):
        sys.setprofile(None)
        threading.setprofile(None)
        # Threads that are still running keep their hook
        self.stopped = True

    def profile_func(self, frame, event, arg):
        if self.stopped or self.thread_state.muted:
            return
        if event == "call":
            self.handle_call_event(frame, arg, is_c_call=False)
        elif event == "return":
            self.handle_return_event(frame, arg, is_c_return=False,
                                     raised=is_unwinding(frame, arg))
        elif event == "c_call":
            self.handle_call_event(frame, arg, is_c_call=True)
        elif event == "c_return":
            self.handle_return_event(frame, arg, is_c_return=True)
        elif event == "c_exception":
            self.handle_return_event(frame, arg, is_c_return=True, raised=True)
        else:
            pass

    def handle_call_event(self, frame, arg, is_c_call=False):
        if is_c_call:
            func_name = callable_name(arg)
            # Retrieve the '__module__' attribute of 'arg', or use '' if it's not available
            module_name = getattr(arg, '__module__', '') or ''
            code = None
            filename = None
            caller_frame = frame
        else:
            code = frame.f_code
            func_name = code.co_name
            # Retrieve the module's name from frame's globals, defaulting to '' if not available
            module_name = frame.f_globals.get('__name__', '') or ''
            filename = resolve_filename(code, None)
            caller_frame = frame.f_back

        # print(f"[DEBUG] handle_call_event: event={'c_call' if is_c_call else 'call'}, func_name={func_name}, module_name={module_name}, filename={filename}")

        if filename:
            filename = os.path.abspath(filename)

        if filename and filename.startswith(self.tracer_dir):
            return

        if not self.tracing_started:
            start_tracing = False
            if filename == self.script_name and code and frame.f_lineno > self.import_end_line:
                start_tracing = True
            else:
                if caller_frame and caller_frame.f_code:
                    caller_filename = resolve_filename(caller_frame.f_code, None)
                    if caller_filename:
                        caller_filename = os.path.abspath(caller_filename)
                    if (caller_filename == self.script_name
                        and caller_frame.f_lineno > self.import_end_line):
                        start_tracing = True

            if not start_tracing:
                return
            self.tracing_started = True

        if func_name == '<module>':
            return

        trace_this = False

        if self.is_stdlib_code(filename):
            if not self.verbose:
                return
            trace_this = True
        else:
            if filename is None:
                # filename is None: C-extension or similar. If verbose, trace anyway.
                if self.verbose:
                    trace_this = True
            else:
                # Normal logic for user-defined or third-party code
                if self.should_trace(filename):
                    trace_this = True
                elif self.verbose and module_name == 'builtins':
                    trace_this = True

        # For a C function, frame is the caller: it belongs to that file
        owner = filename or frame.f_code.co_filename
        trace_this = trace_this and self.file_selected(owner)

        if self.function_exclude and func_name in self.function_exclude:
            self.exclude_depth += 1
        if self.exclude_depth > 0:
            return

        if self.function_filter:
            if func_name in self.function_filter and trace_this:
                self.filter_depth += 1
            if self.filter_depth == 0 or not trace_this:
                return

        if trace_this:
            self.call_stack.append(func_name)

            def_location = filename
            if filename and not is_c_call and code:
                def_location = f"{filename}:{code.co_firstlineno}"

            if caller_frame:
                call_lineno = caller_frame.f_lineno
                call_filename = resolve_filename(caller_frame.f_code, None)
                if call_filename:
                    call_filename = os.path.abspath(call_filename)
            else:
                call_lineno = ''
                call_filename = ''

            arguments = ""
            if self.trace_arguments and not is_c_call and code:
                arguments = format_arguments(frame)

            self.emit_call(func_name, def_location, call_filename, call_lineno,
                           arguments)

            if self.report_mode:
                start_time = time.time()
                if func_name in self.execution_report:
                    _, total_time, call_count = self.execution_report[func_name]
                    self.execution_report[func_name] = (start_time, total_time, call_count + 1)
                else:
                    self.execution_report[func_name] = (start_time, 0, 1)

    def handle_return_event(self, frame, arg, is_c_return, raised=False):
        if not self.tracing_started:
            return

        if is_c_return:
            func_name = callable_name(arg)
            module_name = getattr(arg, '__module__', '') or ''
            code = None
            filename = None
        else:
            code = frame.f_code
            func_name = code.co_name
            module_name = frame.f_globals.get('__name__', '') or ''
            filename = resolve_filename(code, None)

        # # print(f"[DEBUG] handle_return_event: event={'c_return' if is_c_return else 'return'}, func_name={func_name}, module_name={module_name}, filename={filename}")

        if filename:
            filename = os.path.abspath(filename)

        if filename and filename.startswith(self.tracer_dir):
            return

        if func_name == '<module>':
            if (filename == self.script_name
                    and frame.f_globals.get('__name__') == '__main__'):
                # The program is over for this thread.  What it runs from
                # here on is the machinery that started the program.
                self.thread_state.muted = True
            return

        if self.exclude_depth > 0:
            if self.function_exclude and func_name in self.function_exclude:
                self.exclude_depth -= 1
            return

        trace_this = False

        if self.is_stdlib_code(filename):
            if not self.verbose:
                return
            trace_this = True
        else:
            if filename is None:
                if self.verbose and self.call_stack and self.call_stack[-1] == func_name:
                    trace_this = True
            else:
                if self.call_stack and self.call_stack[-1] == func_name:
                    trace_this = True
                else:
                    if self.verbose and module_name == 'builtins':
                        if self.call_stack and self.call_stack[-1] == func_name:
                            trace_this = True

        owner = filename or frame.f_code.co_filename
        trace_this = trace_this and self.file_selected(owner)

        if self.function_filter:
            if self.filter_depth == 0:
                return
            if func_name in self.function_filter and trace_this:
                self.filter_depth -= 1

        if trace_this and self.call_stack and self.call_stack[-1] == func_name:
            if raised:
                # The exception itself is not passed to a profile function
                self.emit_exit(func_name, filename, raised=True)
            elif is_c_return:
                self.emit_exit(func_name, filename)
            else:
                self.emit_exit(func_name, filename, value=arg)

            if self.report_mode and func_name in self.execution_report:
                start_time, total_time, call_count = self.execution_report[func_name]
                exec_time = time.time() - start_time
                self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)

            self.call_stack.pop()

