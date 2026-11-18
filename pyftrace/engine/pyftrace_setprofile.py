import cProfile
import sys
import os
import sysconfig
import threading
from ..tracer import PyftraceBase
from ..utils import resolve_filename, format_arguments, callable_name
from ..utils import is_unwinding, is_function_code

class PyftraceSetprofile(PyftraceBase):
    """
    sys.setprofile based tracer
    """

    def __init__(self, verbose, show_path, report_mode, output_stream, function_filter=None, function_exclude=None, trace_arguments=False):
        super().__init__(verbose, show_path, report_mode, output_stream, function_filter, function_exclude, trace_arguments)

    def setup_tracing(self):
        # sys.setprofile() is per thread: hook the threads started later too
        self.stopped = False
        # Code objects whose calls and returns need no handling at all
        self.ignored_codes = set()
        # C functions are shown with --verbose only, but -e can name one
        # to hide the Python functions it calls back
        self.ignore_c_events = not self.verbose and not self.function_exclude
        self.share_hook()
        threading.setprofile(self.profile_func)
        sys.setprofile(self.profile_func)

    def cleanup_tracing(self):
        self.unshare_hook()
        sys.setprofile(None)
        threading.setprofile(None)
        # Threads that are still running keep their hook
        self.stopped = True

    # A thread has one profile function, and pyftrace needs it.  A
    # program that sets one of its own, to profile itself, would end the
    # trace.  Give the program functions that keep both going.

    def share_hook(self):
        # The profile function of the program, by thread
        self.program_profiles = {}
        self.real_setprofile = sys.setprofile
        self.real_getprofile = sys.getprofile
        self.real_thread_setprofile = threading.setprofile
        sys.setprofile = self.set_program_profile
        sys.getprofile = self.get_program_profile
        threading.setprofile = self.set_thread_profile
        # cProfile sets its function from C, past sys.setprofile().  The
        # trace stands still while it has the hook; take it back after.
        def disable(profiler):
            super(cProfile.Profile, profiler).disable()
            self.real_setprofile(self.profile_func)
        cProfile.Profile.disable = disable

    def unshare_hook(self):
        sys.setprofile = self.real_setprofile
        sys.getprofile = self.real_getprofile
        threading.setprofile = self.real_thread_setprofile
        try:
            del cProfile.Profile.disable
        except AttributeError:
            pass

    def set_program_profile(self, func):
        if func == self.profile_func:
            # threading installs the hook of a new thread this way
            func = None
        ident = threading.get_ident()
        if func is None:
            self.program_profiles.pop(ident, None)
        else:
            self.program_profiles[ident] = func
        self.real_setprofile(self.profile_func)

    def get_program_profile(self):
        return self.program_profiles.get(threading.get_ident())

    def set_thread_profile(self, func):
        # Without a function of the program, new threads still need ours
        self.real_thread_setprofile(func or self.profile_func)

    def call_program_profile(self, frame, event, arg):
        program_profile = self.get_program_profile()
        if program_profile is None:
            return
        # The functions it was set with are ours.  The real ones are
        # written in C and are not seen as Python calls.
        if frame.f_code.co_filename.startswith(self.tracer_dir):
            return
        program_profile(frame, event, arg)

    def profile_func(self, frame, event, arg):
        # This runs for every call the program and its libraries make.
        # Get rid of the ones that cannot matter as cheaply as possible.
        if self.stopped:
            return
        if self.program_profiles:
            self.call_program_profile(frame, event, arg)
        if event == "call" or event == "return":
            if frame.f_code in self.ignored_codes and self.tracing_started:
                return
        elif self.ignore_c_events and self.tracing_started:
            return
        if self.thread_state.muted:
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

    def ignore_code(self, code, filename):
        """
        Whether a Python function is traced depends on where it is
        defined and on the options.  Once it is known that one is not,
        profile_func() does not have to look at it again.
        """
        if code is None:
            return
        # The top-level code of the script ends the trace when it returns
        if filename == self.script_name and code.co_name == '<module>':
            return
        self.ignored_codes.add(code)

    def c_function_traced(self, frame, func):
        """
        Whether a C function that frame calls is traced: a built-in
        when the code calling it is, another one when the module that
        defines it is.  The same answer is needed for its return.
        """
        if not self.verbose:
            return False
        module_name = getattr(func, '__module__', None)
        if module_name in (None, 'builtins'):
            caller = resolve_filename(frame.f_code, None)
            if not caller:
                return False
            caller = os.path.abspath(caller)
            if not self.should_trace(caller):
                return False
            return not (self.is_site_code(caller)
                        and self.run_by_import_system(frame))
        defined_in = resolve_filename(None, func)
        return bool(defined_in) and self.should_trace(os.path.abspath(defined_in))

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

        # Module and class bodies are not traced
        if code and not is_function_code(code):
            self.ignore_code(code, filename)
            return

        # The standard library is left out, with --verbose too
        if self.is_stdlib_code(filename):
            self.ignore_code(code, filename)
            return

        # A library function that the import system runs is left out,
        # but only this time: the program may call it too
        run_for_import = False
        if is_c_call:
            trace_this = self.c_function_traced(frame, arg)
        else:
            trace_this = self.should_trace(filename)
            run_for_import = (trace_this and self.verbose
                              and self.is_site_code(filename)
                              and self.run_by_import_system(caller_frame))

        # For a C function, frame is the caller: it belongs to that file
        owner = filename or frame.f_code.co_filename
        trace_this = trace_this and self.file_selected(owner)

        if not trace_this and func_name not in self.function_exclude:
            self.ignore_code(code, filename)
        if run_for_import:
            trace_this = False

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

            self.report_call(func_name)

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

        if code and not is_function_code(code):
            return

        if self.exclude_depth > 0:
            if self.function_exclude and func_name in self.function_exclude:
                self.exclude_depth -= 1
            return

        if self.is_stdlib_code(filename):
            return

        if is_c_return:
            trace_this = self.c_function_traced(frame, arg)
        else:
            trace_this = self.should_trace(filename)

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

            self.report_return(func_name)

            self.call_stack.pop()

