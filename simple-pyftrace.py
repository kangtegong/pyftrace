import sys
import os
import time
import argparse

class SimplePyftrace:
    def __init__(self):
        self.depth = 0
        self.tool_id = 1
        self.script_name = None
        self.script_dir = None
        self.report_mode = False
        self.execution_report = {}
        self.call_stack = []

    def should_trace(self, file_name):
        if not self.script_name:
            return False
        abs_file_name = os.path.abspath(file_name)
        abs_script_name = os.path.abspath(self.script_name)
        return abs_file_name == abs_script_name

    def get_line_number(self, code, instruction_offset):
        for start, end, lineno in code.co_lines():
            if start <= instruction_offset < end:
                return lineno
        return code.co_firstlineno

    def monitor_call(self, code, instruction_offset, callable_obj, arg0):
        call_lineno = self.get_line_number(code, instruction_offset)
        filename = code.co_filename

        if self.should_trace(filename):
            indent = "    " * self.depth
            func_name = callable_obj.__name__

            # Check if callable_obj has a __code__ attribute
            if hasattr(callable_obj, '__code__'):
                func_def_lineno = callable_obj.__code__.co_firstlineno
                func_info = f"{func_name}:{func_def_lineno}"
                is_builtin = False
            else:
                # For built-in functions or methods
                func_info = func_name
                is_builtin = True

            if not is_builtin:
                # Non-builtin functions (regular Python functions)
                if not self.report_mode:
                    print(f"{indent}Called {func_info} from line {call_lineno}")

                self.depth += 1
                self.call_stack.append(func_name)

                if self.report_mode:
                    start_time = time.time()
                    if func_name in self.execution_report:
                        _, total_time, call_count = self.execution_report[func_name]
                        self.execution_report[func_name] = (start_time, total_time, call_count + 1)
                    else:
                        self.execution_report[func_name] = (start_time, 0, 1)

    def monitor_return(self, code, instruction_offset, retval):
        filename = code.co_filename
        func_name = code.co_name

        if self.should_trace(filename):
            indent = "    " * self.depth

            if func_name != "<module>":
                # Non-builtin functions
                if func_name in self.call_stack:
                    self.depth -= 1
                    if not self.report_mode:
                        print(f"{indent}Returning {func_name}-> {retval}")

                    if self.report_mode and func_name in self.execution_report:
                        start_time, total_time, call_count = self.execution_report[func_name]
                        exec_time = time.time() - start_time
                        self.execution_report[func_name] = (start_time, total_time + exec_time, call_count)

                    # Only pop if we have a matching function on the stack
                    if self.call_stack and self.call_stack[-1] == func_name:
                        self.call_stack.pop()
            else:
                # Handle the module-level code separately
                if not self.report_mode:
                    print(f"{indent}Returning {func_name}-> {retval}")

    def run_python_script(self, script_path):
        print(f"Running script: {script_path}")
        self.script_name = script_path
        self.script_dir = os.path.dirname(os.path.abspath(script_path))

        with open(script_path, "r") as file:
            script_code = file.read()
            code_object = compile(script_code, script_path, 'exec')
            exec(code_object, {"__file__": script_path, "__name__": "__main__"})

    def print_report(self):
        print("\nFunction Name\t| Total Execution Time\t| Call Count")
        print("---------------------------------------------------------")
        for func_name, (_, total_time, call_count) in self.execution_report.items():
            print(f"{func_name:<15}\t| {total_time:.6f} seconds\t| {call_count}")

    def setup_monitoring(self):
        sys.monitoring.use_tool_id(self.tool_id, "simple-pyftrace")
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.CALL, self.monitor_call)
        sys.monitoring.register_callback(self.tool_id, sys.monitoring.events.PY_RETURN, self.monitor_return)
        sys.monitoring.set_events(self.tool_id, sys.monitoring.events.CALL | sys.monitoring.events.PY_RETURN)

    def cleanup_monitoring(self):
        sys.monitoring.free_tool_id(self.tool_id)

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Required python version: 3.12+\n"
            "This script is a simplified version for presentation and is not strictly implemented\n"
            "(e.g., Does not support built-in functions tracing)\n\n"
            "Usage examples:\n"
            "  $ python3 simple-pyftrace.py --report tests/t_fibonacci.py\n"
            "  $ python3 simple-pyftrace.py tests/t_calculator.py\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('script', help="Path to the Python script to run and trace")
    parser.add_argument('--report', action='store_true', help="Generate a report of function execution times")
    args = parser.parse_args()

    tracer = SimplePyftrace()
    tracer.report_mode = args.report

    # Set up monitoring before running the script
    tracer.setup_monitoring()
    tracer.run_python_script(args.script)

    if tracer.report_mode:
        tracer.print_report()

    # Clean up monitoring after execution
    tracer.cleanup_monitoring()

if __name__ == "__main__":
    main()

