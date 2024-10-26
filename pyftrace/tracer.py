import sys
import os
import time
import weakref
from .utils import get_site_packages_modules, timeit

class SimplePyftrace:
    def __init__(self, verbose=False, show_path=False):
        self.depth = 0
        self.tool_id = 1
        self.script_name = None
        self.script_dir = None
        self.report_mode = False
        self.execution_report = {}
        self.call_stack = []
        self.verbose = verbose
        self.show_path = show_path
        self.tracer_script = os.path.abspath(__file__)
        # Set tracer_dir to cover all tracer files
        self.tracer_dir = os.path.dirname(self.tracer_script)
        self.tracing_started = False
        self.site_packages_modules = get_site_packages_modules()
    
    def should_trace(self, file_name):
        if not self.script_dir:
            return False
        abs_file_name = os.path.abspath(file_name)
        if abs_file_name.startswith(self.tracer_dir):
            return False
        return abs_file_name.startswith(self.script_dir)
    
    def is_tracer_code(self, file_name):
        abs_file_name = os.path.abspath(file_name)
        # Check if the file is within the tracer directory
        return abs_file_name.startswith(self.tracer_dir)

    def resolve_filename(self, code, callable_obj):
        filename = ''
        if code and code.co_filename:
            filename = code.co_filename
            if filename.startswith('<frozen ') and filename.endswith('>'):
                module_name = filename[len('<frozen '):-1]
                module = sys.modules.get(module_name)
                if module and hasattr(module, '__file__'):
                    filename = module.__file__
        if not filename and callable_obj:
            if isinstance(callable_obj, weakref.ReferenceType):
                callable_obj = callable_obj()
            module_name = getattr(callable_obj, '__module__', None)
            if module_name:
                module = sys.modules.get(module_name)
                if module and hasattr(module, '__file__'):
                    filename = module.__file__
        return filename
    
    def get_line_number(self, code, instruction_offset):
        if code is None:
            return 0
        for start, end, lineno in code.co_lines():
            if start <= instruction_offset < end:
                return lineno
        return code.co_firstlineno
    
    @timeit
    def monitor_call(self, code, instruction_offset, callable_obj, arg0):
        if not self.tracing_started:
            if code and os.path.abspath(code.co_filename) == os.path.abspath(self.script_name) and code.co_name == '<module>':
                self.tracing_started = True
            else:
                return
        
        call_lineno = self.get_line_number(code, instruction_offset)
        call_filename = self.resolve_filename(code, None)
        
        if isinstance(callable_obj, weakref.ReferenceType):
            callable_obj = callable_obj()
        
        func_name = getattr(callable_obj, '__name__', str(callable_obj))
        module_name = getattr(callable_obj, '__module__', None)
        is_builtin = module_name in (None, 'builtins')
        
        trace_this = False
        if hasattr(callable_obj, '__code__'):
            func_def_lineno = callable_obj.__code__.co_firstlineno
            def_filename = os.path.abspath(callable_obj.__code__.co_filename)
            trace_this = self.should_trace(def_filename) or self.verbose
        else:
            def_filename = self.resolve_filename(None, callable_obj)
            func_def_lineno = ''
            if module_name in self.site_packages_modules or is_builtin:
                trace_this = self.verbose
            else:
                trace_this = self.verbose and self.should_trace(def_filename)
        
        if trace_this and not self.is_tracer_code(call_filename):
            indent = "    " * self.depth
            if self.show_path:
                if is_builtin or not def_filename:
                    func_location = f"{func_name}@{module_name or '<builtin>'}"
                else:
                    func_location = f"{func_name}@{def_filename}:{func_def_lineno}"
                call_location = f"from {call_filename}:{call_lineno}"
            else:
                func_location = func_name
                call_location = f"from line {call_lineno}"
            if not self.report_mode:
                print(f"{indent}Called {func_location} {call_location}")
            self.depth += 1
            self.call_stack.append((func_name, is_builtin))
            if self.report_mode:
                start_time = time.time()
                if func_name in self.execution_report:
                    _, total_time, call_count = self.execution_report[func_name]
                    self.execution_report[func_name] = (start_time, total_time, call_count + 1)
                else:
                    self.execution_report[func_name] = (start_time, 0, 1)
 
    def monitor_py_return(self, code, instruction_offset, retval):
        if not self.tracing_started:
            return

        filename = self.resolve_filename(code, None)
        func_name = code.co_name if code else "<unknown>"

        if func_name == "<module>" and filename == self.tracer_script:
            return

        trace_this = self.should_trace(filename) or self.verbose

        if trace_this and not self.is_tracer_code(filename):
            indent = "    " * self.depth

            if self.call_stack:
                stack_func_name, is_builtin = self.call_stack[-1]
            else:
                stack_func_name = "<unknown>"
                is_builtin = False

            # file path if --path option is used
            if self.show_path:
                file_info = f" @ {filename}" if filename else ""
            else:
                file_info = ""

            if func_name != "<module>":
                if stack_func_name == func_name:
                    self.depth -= 1
                    if not self.report_mode:
                        print(f"{indent}Returning {func_name}-> {retval}{file_info}")

                    if self.report_mode and func_name in self.execution_report:
                        start_time, total_time, call_count = self.execution_report[func_name]
                        exec_time = time.time() - start_time
                        self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)

                    if self.call_stack and self.call_stack[-1][0] == func_name:
                        self.call_stack.pop()
            else:
                if not self.report_mode:
                    print(f"{indent}Returning {func_name}-> {retval}{file_info}")

   
    def monitor_c_return(self, code, instruction_offset, callable_obj, arg0):
        if not self.tracing_started:
            return
        
        func_name = getattr(callable_obj, '__name__', str(callable_obj))
        module_name = getattr(callable_obj, '__module__', None)
        is_builtin = module_name in (None, 'builtins')
        filename = self.resolve_filename(code, callable_obj)
        
        trace_this = self.verbose and (self.should_trace(filename) or is_builtin)
        
        if trace_this and not self.is_tracer_code(filename):
            indent = "    " * self.depth
            if self.call_stack:
                stack_func_name, is_builtin = self.call_stack[-1]
            else:
                stack_func_name = "<unknown>"
                is_builtin = True
            if self.show_path:
                file_info = f" @ {filename}" if filename else ""
            else:
                file_info = ""
            if stack_func_name == func_name:
                self.depth -= 1
                if not self.report_mode:
                    print(f"{indent}Returning {func_name}{file_info}")
                if self.report_mode and func_name in self.execution_report:
                    start_time, total_time, call_count = self.execution_report[func_name]
                    exec_time = time.time() - start_time
                    self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)
                if self.call_stack and self.call_stack[-1][0] == func_name:
                    self.call_stack.pop()
    
    def run_python_script(self, script_path):
        print(f"Running script: {script_path}")
        self.script_name = script_path
        self.script_dir = os.path.dirname(os.path.abspath(script_path))
        
        with open(script_path, "r") as file:
            script_code = file.read()
            code_object = compile(script_code, script_path, 'exec')
        
        old_sys_path = sys.path.copy()
        sys.path.insert(0, self.script_dir)
        
        self.setup_monitoring()
        
        try:
            exec(code_object, {"__file__": script_path, "__name__": "__main__"})
        finally:
            sys.path = old_sys_path
            self.cleanup_monitoring()
    
    def print_report(self):
        print("\nFunction Name\t| Total Execution Time\t| Call Count")
        print("---------------------------------------------------------")
        for func_name, (_, total_time, call_count) in self.execution_report.items():
            print(f"{func_name:<15}\t| {total_time:.6f} seconds\t| {call_count}")
    
    def setup_monitoring(self):
        sys.monitoring.use_tool_id(self.tool_id, "simple-pyftrace")
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.CALL, self.monitor_call)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_RETURN, self.monitor_py_return)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.C_RETURN, self.monitor_c_return)
        sys.monitoring.set_events(
            self.tool_id,
            sys.monitoring.events.CALL | sys.monitoring.events.PY_RETURN
        )
    
    def cleanup_monitoring(self):
        sys.monitoring.free_tool_id(self.tool_id)

