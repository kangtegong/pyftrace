import unittest
import subprocess
import sys
import os
import re
import json
import importlib.util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pyftrace import __version__ as pyftrace_version

class PyftraceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Set up the test environment.
        """
        cls.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        cls.pyftrace_module = 'pyftrace.main'
        cls.python_executable = sys.executable
        cls.foobar_script = os.path.join(cls.project_root, 'examples', 'foobar.py')
        cls.main_script = os.path.join(cls.project_root, 'examples', 'module_trace', 'main_script.py')
        cls.module_a = os.path.join(cls.project_root, 'examples', 'module_trace', 'module_a.py')
        cls.module_b = os.path.join(cls.project_root, 'examples', 'module_trace', 'module_b.py')
        cls.exception_script = os.path.join(cls.project_root, 'examples', 'exception.py')
        cls.recursive_script = os.path.join(cls.project_root, 'examples', 'recursives.py')
        cls.loop_script = os.path.join(cls.project_root, 'examples', 'loop.py')
        cls.threads_script = os.path.join(cls.project_root, 'examples', 'threads.py')
        cls.processes_script = os.path.join(cls.project_root, 'examples', 'processes.py')
        cls.callback_script = os.path.join(cls.project_root, 'examples', 'callback.py')
        cls.generator_script = os.path.join(cls.project_root, 'examples', 'generator.py')
        cls.add_script = os.path.join(cls.project_root, 'examples', 'add.py')
        cls.temp_output = os.path.join(cls.project_root, 'tests', 'tmp_output.txt')

    def setUp(self):
        """
        Initialize output and error for each test.
        """
        self.output = ""
        self.error = ""

    def tearDown(self):
        """
        Print output and error after each test.
        """
        if os.path.exists(getattr(self, "temp_output", "")):
            try:
                os.remove(self.temp_output)
            except Exception:
                pass
        if self.output:
            print("\nSTDOUT:")
            print(self.output)
        if self.error:
            print("\nSTDERR:")
            print(self.error)

    def run_pyftrace(self, args):
        """
        Helper method to run the pyftrace command with given arguments.

        Args:
            args (list): List of command-line arguments.

        Returns:
            subprocess.CompletedProcess: The result of the subprocess.run() execution.
        """
        cmd = [self.python_executable, '-m', self.pyftrace_module] + args
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.project_root,
            text=True
        )
        self.output = result.stdout
        self.error = result.stderr
        return result

    def normalize_output(self, text):
        """
        Normalize text by trimming lines, reducing spaces, and unifying line endings.
        """
        # Normalize paths, trim lines, and reduce multiple spaces
        normalized = '\n'.join(' '.join(line.strip().split()) for line in text.strip().splitlines())
        # Standardize path separators for Windows
        normalized = normalized.replace("\r\n", "\n").replace("\\", "/")
        return normalized

class PyftraceTests(PyftraceTestCase):
    def test_version_flag_short_v(self):
        """
        Test '-V' flag for version display.
        """
        result = self.run_pyftrace(['-V'])
        expected_output = f"pyftrace version {pyftrace_version}"
        self.assertIn(expected_output, result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_version_flag_long_version(self):
        """
        Test '--version' flag for version display.
        """
        result = self.run_pyftrace(['--version'])
        expected_output = f"pyftrace version {pyftrace_version}"
        self.assertIn(expected_output, result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_help_option_short_h(self):
        """
        Test '-h' flag for help message.
        """
        result = self.run_pyftrace(['-h'])
        self.assertIn("usage:", result.stdout)
        self.assertIn("pyftrace: Python function tracing tool.", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_help_option_long_help(self):
        """
        Test '--help' flag for help message.
        """
        result = self.run_pyftrace(['--help'])
        self.assertIn("usage:", result.stdout)
        self.assertIn("pyftrace: Python function tracing tool.", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_tracing_script_default(self):
        """
        Test basic tracing without additional flags.
        """
        args = [self.main_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called main from line 10
        Called function_a from line 5
    Function A is called.
        Returning function_a-> ret_a
        Called function_b from line 6
    Function B is called.
        Returning function_b-> ret_b
    Results: ret_a, ret_b
    Returning main-> None"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_tracing_script_verbose(self):
        """
        Test '--verbose' flag for detailed tracing.
        """
        args = [self.main_script, '--verbose']
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called main from line 10
        Called function_a from line 5
            Called print from line 2
    Function A is called.
            Returning print
        Returning function_a-> ret_a
        Called function_b from line 6
            Called print from line 2
    Function B is called.
            Returning print
        Returning function_b-> ret_b
        Called print from line 7
    Results: ret_a, ret_b
        Returning print
    Returning main-> None"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_argument_tracing(self):
        """
        Test '--argument' flag for showing function arguments.
        """
        args = ['--argument', self.add_script, '3', '5']
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.add_script}
    Called add (a=3.0, b=5.0) from line 18
    Returning add-> 8.0
The sum of 3.0 and 5.0 is 8.0"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_output_file(self):
        """
        Test '--output' flag writes tracing to file.
        """
        args = ['--argument', '--output', self.temp_output, self.add_script, '2', '4']
        result = self.run_pyftrace(args)

        with open(self.temp_output, 'r') as f:
            file_content = f.read()

        normalized_file = self.normalize_output(file_content)
        expected_output = f"""Running script: {self.add_script}
    Called add (a=2.0, b=4.0) from line 18
    Returning add-> 6.0"""

        normalized_expected = self.normalize_output(expected_output)

        self.assertEqual(normalized_expected, normalized_file)
        # the script's own output is not part of the trace
        self.assertEqual(result.stdout.strip(), "The sum of 2.0 and 4.0 is 6.0")
        self.assertEqual(result.returncode, 0)

    def test_module(self):
        """
        Test '-m' flag for tracing a module.
        """
        args = ['-m', 'examples.add', '3', '5']
        result = self.run_pyftrace(args)

        expected_output = """Running module: examples.add
    Called add from line 18
    Returning add-> 8.0
The sum of 3.0 and 5.0 is 8.0"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_module_arguments(self):
        """
        Test that options after '-m <module>' go to the module.
        """
        args = ['-m', 'examples.add', '3', '5', '--verbose']
        result = self.run_pyftrace(args)

        self.assertIn("Usage: python add.py", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_module_not_found(self):
        """
        Test '-m' flag with a module that does not exist.
        """
        result = self.run_pyftrace(['-m', 'examples.no_such_module'])

        self.assertIn("No module named", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_max_lines(self):
        """
        Test '--max-lines' flag for truncating the trace.
        """
        args = ['--max-lines', '3', self.foobar_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.foobar_script}
    Called foo from line 9
        Called bar from line 2
        Returning bar-> 6
... trace truncated after 3 lines"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_exception(self):
        """
        Test that a function left by an exception is unwound.
        """
        result = self.run_pyftrace([self.exception_script])

        expected_output = f"""Running script: {self.exception_script}
    Called safe_load from line 13
        Called load from line 9
            Called parse from line 5
            Returning parse-> 1
        Returning load-> 2
    Returning safe_load-> 2
    Called safe_load from line 14
        Called load from line 9
            Called parse from line 5
            Raised parse
        Raised load
    Returning safe_load-> -1"""

        # Only the sys.monitoring engine knows which exception it was
        actual = re.sub(r"(Raised \w+)-> .*", r"\1", result.stdout)
        if sys.version_info >= (3, 12):
            self.assertIn("Raised parse-> ValueError: invalid literal", result.stdout)

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(actual)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_function_filter(self):
        """
        Test '--function' flag for tracing a single function.
        """
        args = ['--function', 'function_a', self.main_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called function_a from line 5
Function A is called.
    Returning function_a-> ret_a
Function B is called.
Results: ret_a, ret_b"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_function_filter_recursive(self):
        """
        Test that '--function' stays open until the outermost call returns.
        """
        args = ['--function', 'countdown', self.recursive_script]
        result = self.run_pyftrace(args)

        self.assertEqual(result.stdout.count("Called countdown"), 51)
        self.assertEqual(result.stdout.count("Returning countdown"), 51)
        self.assertEqual(result.returncode, 0)

    def test_function_filter_multiple(self):
        """
        Test '--function' given more than once.
        """
        args = ['-f', 'function_a', '-f', 'function_b', self.main_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called function_a from line 5
Function A is called.
    Returning function_a-> ret_a
    Called function_b from line 6
Function B is called.
    Returning function_b-> ret_b
Results: ret_a, ret_b"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_exclude_function_multiple(self):
        """
        Test '--exclude-function' given more than once.
        """
        args = ['-e', 'function_a', '-e', 'function_b', self.main_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called main from line 10
Function A is called.
Function B is called.
Results: ret_a, ret_b
    Returning main-> None"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_file_filter(self):
        """
        Test '--file' flag for tracing the functions of one file.
        """
        args = ['--file', self.module_a, self.main_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called function_a from line 5
Function A is called.
    Returning function_a-> ret_a
Function B is called.
Results: ret_a, ret_b"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_file_filter_module_name(self):
        """
        Test '--file' flag with a module name instead of a path.
        """
        args = ['--file', 'module_a', self.main_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called function_a from line 5
Function A is called.
    Returning function_a-> ret_a
Function B is called.
Results: ret_a, ret_b"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_exclude_file(self):
        """
        Test '--exclude-file' flag with a glob pattern.
        """
        args = ['--exclude-file', 'examples/*/module_a.py', self.main_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.main_script}
    Called main from line 10
Function A is called.
        Called function_b from line 6
Function B is called.
        Returning function_b-> ret_b
Results: ret_a, ret_b
    Returning main-> None"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_format_json(self):
        """
        Test '--format json' for machine-readable output.
        """
        args = ['--format', 'json', self.foobar_script]
        result = self.run_pyftrace(args)

        events = [json.loads(line) for line in result.stdout.splitlines()]
        expected_events = [
            {"event": "start", "script": self.foobar_script},
            {"event": "call", "depth": 1, "function": "foo", "line": 9},
            {"event": "call", "depth": 2, "function": "bar", "line": 2},
            {"event": "return", "depth": 2, "function": "bar", "value": "6"},
            {"event": "call", "depth": 2, "function": "bar", "line": 3},
            {"event": "return", "depth": 2, "function": "bar", "value": "14"},
            {"event": "return", "depth": 1, "function": "foo", "value": "10"},
        ]

        self.assertEqual(expected_events, events)
        self.assertEqual(result.returncode, 0)

    def test_collapse(self):
        """
        Test '--collapse' flag for folding repeated calls.
        """
        args = ['--collapse', self.loop_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.loop_script}
    Called run from line 8
        Called tick from line 6
        Returning tick-> tock
        ... repeated 999 more times
    Returning run-> None"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_threads(self):
        """
        Test that a thread is traced on its own call stack.
        """
        result = self.run_pyftrace([self.threads_script])

        expected_output = f"""Running script: {self.threads_script}
    Called main from line 15
[tid N]     Called worker from line N
[tid N]         Called square from line 7
[tid N]         Returning square-> 9
[tid N]     Returning worker-> 9
        Called square from line 13
        Returning square-> 16
    Returning main-> 16"""

        # The thread id and the line in threading.py that calls worker vary
        actual = re.sub(r"\[tid \d+\]", "[tid N]", result.stdout)
        actual = re.sub(r"(Called worker from line) \d+", r"\1 N", actual)

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(actual)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def check_processes(self, extra_args):
        result = self.run_pyftrace(extra_args + [self.processes_script])
        trace = result.stdout
        if '--output' in extra_args:
            with open(self.temp_output, 'r') as f:
                trace = f.read()

        expected_output = f"""Running script: {self.processes_script}
    Called main from line 16
[pid N]     Called worker from line N
[pid N]         Called square from line 7
[pid N]         Returning square-> 9
[pid N]     Returning worker-> 9
        Called square from line 13
        Returning square-> 16
    Returning main-> 16"""

        # The pid and the line in multiprocessing that calls worker vary
        actual = re.sub(r"\[pid \d+\]", "[pid N]", trace)
        actual = re.sub(r"(Called worker from line) \d+", r"\1 N", actual)

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(actual)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_processes(self):
        """
        Test that a child process started by multiprocessing is traced.
        """
        self.check_processes([])

    def test_processes_report(self):
        """
        Test that '--report' includes the calls made in a child process.
        """
        args = ['--report', '--format', 'json', self.processes_script]
        result = self.run_pyftrace(args)

        calls = {}
        for line in result.stdout.splitlines():
            event = json.loads(line)
            if event["event"] == "report":
                calls[event["function"]] = event["calls"]

        # worker() runs in the child only, square() once in each process
        self.assertEqual({"main": 1, "worker": 1, "square": 2}, calls)
        self.assertEqual(result.returncode, 0)

    def test_processes_output_file(self):
        """
        Test that a child process writes its trace to the '--output' file.
        """
        self.check_processes(['--output', self.temp_output])

    def test_callback(self):
        """
        Test that a function called from C code, here map(), is traced.
        """
        result = self.run_pyftrace([self.callback_script])

        expected_output = f"""Running script: {self.callback_script}
    Called total from line 7
        Called square from line 5
        Returning square-> 1
        Called square from line 5
        Returning square-> 4
    Returning total-> 5"""

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(result.stdout)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_generator(self):
        """
        Test that a suspended generator is not on the call stack.
        """
        result = self.run_pyftrace([self.generator_script])

        expected_output = f"""Running script: {self.generator_script}
    Called numbers from line 8
    Returning numbers-> 1
    Called show from line 9
    Returning show-> 1
    Called numbers from line 8
    Returning numbers-> 2
    Called show from line 9
    Returning show-> 2
    Called numbers from line 8
    Returning numbers-> None"""

        self.assertEqual(self.normalize_output(expected_output),
                         self.normalize_output(result.stdout))
        # No call may be nested under the generator
        self.assertNotIn("        Called", result.stdout)
        self.assertEqual(result.returncode, 0)

    # def test_tracing_script_path(self):
    #     """
    #     Test '--path' flag to include file paths in tracing.
    #     """
    #     args = [self.main_script, '--path']
    #     result = self.run_pyftrace(args)

    #     expected_output = f"""Running script: {self.main_script}
    # Called main@{self.main_script}:4 from {self.main_script}:10
    #     Called function_a@{self.module_a}:1 from {self.main_script}:5
    # Function A is called.
    #     Returning function_a-> ret_a @ {self.module_a}
    #     Called function_b@{self.module_b}:1 from {self.main_script}:6
    # Function B is called.
    #     Returning function_b-> ret_b @ {self.module_b}
    # Results: ret_a, ret_b
    # Returning main-> None @ {self.main_script}"""

    #     normalized_expected = self.normalize_output(expected_output)
    #     normalized_actual = self.normalize_output(result.stdout)

    #     self.assertEqual(normalized_expected, normalized_actual)
    #     self.assertEqual(result.returncode, 0)


    # def test_tracing_script_report(self):
    #     """
    #     Test '--report' flag for generating execution reports.
    #     """
    #     args = [self.main_script, '--report']
    #     result = self.run_pyftrace(args)

    #     # Define the expected run output section
    #     expected_run_output = f"""Running script: {self.main_script}
    # Function A is called.
    # Function B is called.
    # Results: ret_a, ret_b"""

    #     # Define regex pattern for the report section
    #     report_header = r"Function Name\s+\|\s+Total Execution Time\s+\|\s+Call Count"
    #     report_separator = r"-+"
    #     report_entries = [
    #         r"main\s+\|\s+\d+\.\d+ seconds\s+\|\s+1",
    #         r"function_a\s+\|\s+\d+\.\d+ seconds\s+\|\s+1",
    #         r"function_b\s+\|\s+\d+\.\d+ seconds\s+\|\s+1",
    #     ]

    #     # Combine the report section into a single regex pattern
    #     report_pattern = (
    #         report_header + r"\n" +
    #         report_separator + r"\n" +
    #         "\n".join(report_entries)
    #     )

    #     # Combine the entire expected output regex
    #     expected_output_pattern = (
    #         re.escape(expected_run_output) +
    #         r"\n\n" +
    #         report_pattern
    #     )

    #     # Normalize line endings and strip trailing whitespace
    #     actual_output = result.stdout.replace('\r\n', '\n').strip()

    #     # Remove any leading/trailing whitespace in expected pattern
    #     expected_output_pattern = expected_output_pattern.strip()

    #     # Use re.DOTALL to allow multi-line matching
    #     self.assertRegex(actual_output, expected_output_pattern)
    #     self.assertEqual(result.returncode, 0)

def has_module(name):
    return importlib.util.find_spec(name) is not None

class RealWorldExampleTests(PyftraceTestCase):
    """
    Trace the examples that are built on large libraries.  A test is
    skipped where its library is not installed.
    """

    def trace_example(self, name):
        """
        Run an example with '--format json' and return its events as
        (event, depth, function) tuples, down to depth 3.  Line numbers
        and values depend on the version of the library and are left
        out.  So are the events of child processes, which a library may
        or may not start.
        """
        script = os.path.join(self.project_root, 'examples', name)
        result = self.run_pyftrace(['--format', 'json', script])
        self.assertEqual(result.returncode, 0)

        self.events = []
        for line in result.stdout.splitlines():
            if not line.startswith('{"event"'):
                continue
            event = json.loads(line)
            if "depth" in event and "pid" not in event:
                self.events.append(event)
        return [(event["event"], event["depth"], event["function"])
                for event in self.events if event["depth"] <= 3]

    @staticmethod
    def call(depth, function, children=()):
        """
        The events of a call that returns, with those of its callees.
        """
        events = [("call", depth, function)]
        for child in children:
            events += child
        return events + [("return", depth, function)]

    @unittest.skipUnless(has_module("django"), "Django is not installed")
    def test_django_example(self):
        """
        Test that only the application code of a Django request is traced.
        """
        call = self.call
        request_list = call(2, "__call__", [
            call(3, "article_list"),
        ])
        request_detail = call(2, "__call__", [
            call(3, "article_detail"),
        ])
        # find_article() raises Http404, Django turns it into a response
        request_missing = call(2, "__call__", [
            [("call", 3, "article_detail"), ("raise", 3, "article_detail")],
        ])
        expected_events = call(1, "main", [
            call(2, "__init__"),
            request_list,
            request_detail,
            request_missing,
        ])

        self.assertEqual(expected_events,
                         self.trace_example('django_example.py'))

        raised = [event for event in self.events if event["event"] == "raise"]
        self.assertEqual(["find_article", "article_detail"],
                         [event["function"] for event in raised])
        if sys.version_info >= (3, 12):
            self.assertEqual("Http404: No article 99", raised[0]["exception"])

    @unittest.skipUnless(has_module("torch"), "PyTorch is not installed")
    def test_pytorch_example(self):
        """
        Test that the structure of a PyTorch training loop is traced.
        """
        call = self.call
        epoch = call(2, "train_epoch", [call(3, "train_step")] * 4)
        expected_events = call(1, "main", [
            call(2, "__init__"),
            epoch,
            epoch,
            epoch,
            call(2, "evaluate", [call(3, "make_batch"), call(3, "forward")]),
        ])

        self.assertEqual(expected_events,
                         self.trace_example('pytorch_example.py'))

        # forward() is called by PyTorch: once per step and once to evaluate
        forward_calls = [event for event in self.events
                         if event["event"] == "call"
                         and event["function"] == "forward"]
        self.assertEqual(13, len(forward_calls))

if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(PyftraceTests),
        loader.loadTestsFromTestCase(RealWorldExampleTests),
    ])
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        print("\nPASS")
