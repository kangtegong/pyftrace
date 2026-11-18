import unittest
import subprocess
import sys
import os
import re
import json
import importlib.util
import random
import select
import shutil
import signal
import site
import sysconfig
import tempfile
import textwrap
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pyftrace import __version__ as pyftrace_version
from pyftrace.output import Collapser
from pyftrace.tracer import get_tracer
from pyftrace.utils import normalize_patterns

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

    def run_pyftrace(self, args, cwd=None):
        """
        Helper method to run the pyftrace command with given arguments.

        Args:
            args (list): List of command-line arguments.
            cwd (str): Directory to run in instead of the project root.

        Returns:
            subprocess.CompletedProcess: The result of the subprocess.run() execution.
        """
        cmd = [self.python_executable, '-m', self.pyftrace_module] + args
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd or self.project_root,
            # pyftrace is run from the source tree, wherever the command runs
            env=dict(os.environ, PYTHONPATH=self.python_path()),
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

    def python_path(self):
        """
        The source tree first, then what PYTHONPATH already holds, such
        as the place of a dependency that the interpreter lacks.
        """
        paths = [self.project_root]
        if os.environ.get("PYTHONPATH"):
            paths.append(os.environ["PYTHONPATH"])
        return os.pathsep.join(paths)

    def run_source(self, source, args=(), script_args=()):
        """
        Run pyftrace on a script given as source text.  The script is
        written to a temporary directory that is removed after the test.
        """
        directory = tempfile.mkdtemp(prefix="pyftrace-test-")
        self.addCleanup(shutil.rmtree, directory, True)
        self.script = os.path.join(directory, "script.py")
        with open(self.script, "w") as f:
            f.write(textwrap.dedent(source))
        return self.run_pyftrace(list(args) + [self.script] + list(script_args))

    @staticmethod
    def trace_lines(text):
        """
        The trace lines in the output of pyftrace, with their
        indentation.  What varies from run to run is replaced: pids,
        tids, the line of a call made from library code, and the
        exception named in a 'Raised' line, which only one engine knows.
        """
        lines = []
        for line in text.splitlines():
            if not re.search(r"(Called|Returning|Raised) |^\.\.\. | \.\.\. ", line):
                continue
            line = re.sub(r"\[pid \d+", "[pid N", line)
            line = re.sub(r"tid \d+\]", "tid N]", line)
            line = re.sub(r"(Raised \w+)-> .*", r"\1", line)
            lines.append(line.rstrip())
        return lines

    def report_calls(self, result):
        """
        The rows of a '--report --format json' run as {function: event}.
        """
        rows = {}
        for line in result.stdout.splitlines():
            if line.startswith('{"event": "report"'):
                event = json.loads(line)
                rows[event["function"]] = event
        return rows

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

    def run_into_head(self, args, lines):
        """
        Run pyftrace with its output piped into a reader that takes a
        number of lines and closes the pipe.
        """
        cmd = [self.python_executable, '-m', self.pyftrace_module] + args
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=self.project_root,
                                   universal_newlines=True)
        head = [process.stdout.readline() for _ in range(lines)]
        process.stdout.close()
        stderr = process.stderr.read()
        process.stderr.close()
        return head, stderr, process.wait()

    def test_reader_closes_pipe(self):
        """
        'pyftrace script.py | head' ends the trace, not the program.
        """
        script = os.path.join(self.project_root, 'examples', 'loop.py')
        head, stderr, status = self.run_into_head([script], 3)

        self.assertIn("Called run", head[1])
        self.assertEqual("", stderr)
        self.assertEqual(0, status)

    def test_run_as_package(self):
        """
        'python -m pyftrace' is the same command as 'pyftrace', run by
        an interpreter of the caller's choice.
        """
        cmd = [self.python_executable, '-m', 'pyftrace', self.foobar_script]
        result = subprocess.run(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=self.project_root,
                                universal_newlines=True)

        self.assertIn("Called foo", result.stdout)
        self.assertNotIn("Called main", result.stdout)
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
        # An environment may have import hooks in site-packages, which
        # --verbose would show for every import.  Stay within the examples.
        examples = os.path.join(self.project_root, 'examples')
        args = ['--verbose', '--file', examples, self.main_script]
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

    def test_processes_max_lines(self):
        """
        Test that '--max-lines' limits the lines of all processes together.
        """
        args = ['--max-lines', '3', self.processes_script]
        result = self.run_pyftrace(args)

        expected_output = f"""Running script: {self.processes_script}
    Called main from line 16
[pid N]     Called worker from line N
[pid N]         Called square from line 7
... trace truncated after 3 lines"""

        actual = re.sub(r"\[pid \d+\]", "[pid N]", result.stdout)
        actual = re.sub(r"(Called worker from line) \d+", r"\1 N", actual)

        normalized_expected = self.normalize_output(expected_output)
        normalized_actual = self.normalize_output(actual)

        self.assertEqual(normalized_expected, normalized_actual)
        self.assertEqual(result.returncode, 0)

    def test_processes_max_lines_exact(self):
        """
        Processes that print at the same moment do not get past
        '--max-lines' together.
        """
        result = self.run_source("""
            import multiprocessing

            def tick(n):
                return n

            def flood(start):
                start.wait()
                for n in range(300):
                    tick(n)

            if __name__ == "__main__":
                start = multiprocessing.Event()
                workers = [multiprocessing.Process(target=flood, args=(start,))
                           for _ in range(4)]
                for worker in workers:
                    worker.start()
                start.set()
                for worker in workers:
                    worker.join()
        """, args=['--max-lines', '100'])

        lines = result.stdout.splitlines()[1:]
        notices = [line for line in lines if "truncated" in line]
        self.assertEqual(101, len(lines))
        self.assertEqual(["... trace truncated after 100 lines"], notices)

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

class OptionTests(PyftraceTestCase):
    """
    What each command line option does on its own.
    """

    def test_path(self):
        """
        Test '--path' flag for showing where functions are defined and called.
        """
        result = self.run_pyftrace(['--path', self.foobar_script])
        script = self.foobar_script

        self.assertEqual([
            f"    Called foo@{script}:1 from {script}:9",
            f"        Called bar@{script}:6 from {script}:2",
            f"        Returning bar-> 6 @ {script}",
            f"        Called bar@{script}:6 from {script}:3",
            f"        Returning bar-> 14 @ {script}",
            f"    Returning foo-> 10 @ {script}",
        ], self.trace_lines(result.stdout))
        self.assertEqual(result.returncode, 0)

    def test_path_json(self):
        """
        Test that '--format json' carries the '--path' information as fields.
        """
        args = ['--path', '--format', 'json', self.foobar_script]
        result = self.run_pyftrace(args)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        script = self.foobar_script

        self.assertEqual({"event": "call", "depth": 1, "function": "foo",
                          "line": 9, "defined_at": f"{script}:1",
                          "caller_file": script}, events[1])
        self.assertEqual({"event": "return", "depth": 1, "function": "foo",
                          "value": "10", "file": script}, events[-1])

    def test_depth(self):
        """
        Test '--depth' flag for limiting the depth of the trace.
        """
        result = self.run_pyftrace(['--depth', '1', self.foobar_script])

        self.assertEqual([
            "    Called foo from line 9",
            "    Returning foo-> 10",
        ], self.trace_lines(result.stdout))

    def test_max_lines_not_reached(self):
        """
        Test that '--max-lines' prints no marker for a trace that fits.
        """
        result = self.run_pyftrace(['--max-lines', '6', self.foobar_script])

        self.assertEqual(6, len(self.trace_lines(result.stdout)))
        self.assertNotIn("truncated", result.stdout)

    def test_report(self):
        """
        Test '--report' flag for the table of execution times.
        """
        result = self.run_pyftrace(['--report', self.foobar_script])

        self.assertIn("Function Name", result.stdout)
        self.assertRegex(result.stdout, r"foo\s+\|\s+\d+\.\d+ seconds\s+\|\s+1")
        self.assertRegex(result.stdout, r"bar\s+\|\s+\d+\.\d+ seconds\s+\|\s+2")
        # The report replaces the trace
        self.assertEqual([], self.trace_lines(result.stdout))
        self.assertEqual(result.returncode, 0)

    def test_report_after_exit(self):
        """
        A program that ends with sys.exit() still gets its report, and
        its exit status is kept.  pytest and unittest end this way.
        """
        result = self.run_source("""
            import sys

            def work():
                return 1

            work()
            sys.exit(3)
        """, args=['--report'])

        self.assertRegex(result.stdout, r"work\s+\|\s+\d+\.\d+ seconds\s+\|\s+1")
        self.assertEqual(result.returncode, 3)

    def test_report_after_exception(self):
        """
        A program that dies of an exception still gets its report.
        """
        result = self.run_source("""
            def work():
                raise KeyError("missing")

            work()
        """, args=['--report'])

        self.assertRegex(result.stdout, r"work\s+\|\s+\d+\.\d+ seconds\s+\|\s+1")
        self.assertIn("KeyError", result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_report_json(self):
        """
        Test '--report' with '--format json'.
        """
        args = ['--report', '--format', 'json', self.foobar_script]
        rows = self.report_calls(self.run_pyftrace(args))

        self.assertEqual({"foo": 1, "bar": 2},
                         {name: row["calls"] for name, row in rows.items()})

    def test_report_recursive(self):
        """
        Test that '--report' counts the time of a recursive function once.
        """
        result = self.run_source("""
            import time

            def nap(depth):
                time.sleep(0.02)
                if depth:
                    nap(depth - 1)

            def main():
                nap(4)

            main()
        """, ['--report', '--format', 'json'])
        rows = self.report_calls(result)

        self.assertEqual(5, rows["nap"]["calls"])
        # Five nested calls sleep for 0.1 seconds in all
        self.assertGreater(rows["nap"]["seconds"], 0.09)
        # All of nap() runs within main()
        self.assertLessEqual(rows["nap"]["seconds"], rows["main"]["seconds"])

    def test_exclude_function(self):
        """
        Test '--exclude-function' flag for hiding a function.
        """
        args = ['--exclude-function', 'bar', self.foobar_script]
        result = self.run_pyftrace(args)

        self.assertEqual([
            "    Called foo from line 9",
            "    Returning foo-> 10",
        ], self.trace_lines(result.stdout))

    def test_exclude_function_recursive(self):
        """
        Test that '--exclude-function' hides all levels of a recursion.
        """
        result = self.run_source("""
            def leaf(n):
                return n

            def fact(n):
                if n <= 1:
                    return leaf(1)
                value = n * fact(n - 1)
                leaf(value)
                return value

            def other():
                return leaf(0)

            fact(3)
            other()
        """, ['--exclude-function', 'fact'])

        self.assertEqual([
            "    Called other from line 16",
            "        Called leaf from line 13",
            "        Returning leaf-> 0",
            "    Returning other-> 0",
        ], self.trace_lines(result.stdout))

    def test_exclude_function_callback(self):
        """
        Test that excluding a C function hides the functions it calls back.
        """
        result = self.run_source("""
            def square(n):
                return n * n

            def total(values):
                return sum(map(square, values))

            sorted([2, 1], key=square)
            total([3])
        """, ['--exclude-function', 'sorted'])

        self.assertEqual([
            "    Called total from line 9",
            "        Called square from line 6",
            "        Returning square-> 9",
            "    Returning total-> 9",
        ], self.trace_lines(result.stdout))

    def test_collapse_nested(self):
        """
        Test that '--collapse' folds a repeated call that contains repeats.
        """
        result = self.run_source("""
            def leaf():
                return 0

            def row():
                for _ in range(3):
                    leaf()

            def table():
                for _ in range(4):
                    row()

            table()
        """, ['--collapse'])

        self.assertEqual([
            "    Called table from line 13",
            "        Called row from line 11",
            "            Called leaf from line 7",
            "            Returning leaf-> 0",
            "            ... repeated 2 more times",
            "        Returning row-> None",
            "        ... repeated 3 more times",
            "    Returning table-> None",
        ], self.trace_lines(result.stdout))

    def test_collapse_json(self):
        """
        Test that '--collapse' reports the count as an event of its own.
        """
        args = ['--collapse', '--format', 'json', self.loop_script]
        result = self.run_pyftrace(args)
        events = [json.loads(line) for line in result.stdout.splitlines()]

        self.assertIn({"event": "repeat", "depth": 2, "count": 999}, events)
        self.assertEqual(6, len(events))

    def test_verbose_builtin_raises(self):
        """
        Test that '--verbose' shows a C function that raises.
        """
        result = self.run_source("""
            def size(value):
                try:
                    return len(value)
                except TypeError:
                    return 0

            size(None)
        """, ['--verbose'])

        self.assertEqual([
            "    Called size from line 8",
            "        Called len from line 4",
            "        Raised len",
            "    Returning size-> 0",
        ], self.trace_lines(result.stdout))

    def test_module_package(self):
        """
        Test '-m' with a package, which runs its __main__ module.
        """
        directory = tempfile.mkdtemp(prefix="pyftrace-test-")
        self.addCleanup(shutil.rmtree, directory, True)
        package = os.path.join(directory, "shapes")
        os.mkdir(package)
        with open(os.path.join(package, "__init__.py"), "w") as f:
            f.write("def area(side):\n    return side * side\n")
        with open(os.path.join(package, "__main__.py"), "w") as f:
            f.write("import sys\nfrom shapes import area\n\n"
                    "def main(argv):\n    print(area(int(argv[0])))\n\n"
                    "main(sys.argv[1:])\n")

        result = self.run_pyftrace(['-m', 'shapes', '7'], cwd=directory)

        self.assertEqual("Running module: shapes", result.stdout.splitlines()[0])
        self.assertEqual([
            "    Called main from line 7",
            "        Called area from line 5",
            "        Returning area-> 49",
            "    Returning main-> None",
        ], self.trace_lines(result.stdout))

        # The package can also be named to -F, which selects all its files
        result = self.run_pyftrace(['-E', 'shapes', '-m', 'shapes', '7'],
                                   cwd=directory)
        self.assertEqual([], self.trace_lines(result.stdout))
        self.assertIn("49", result.stdout)

    def test_script_arguments_and_exit_code(self):
        """
        Test that the script gets its arguments and decides the exit code.
        """
        result = self.run_source("""
            import sys

            def main(argv):
                sys.exit(len(argv))

            main(sys.argv)
        """, script_args=['one', 'two'])

        self.assertEqual(result.returncode, 3)
        self.assertEqual([
            "    Called main from line 7",
            "    Raised main",
        ], self.trace_lines(result.stdout))

    def test_missing_script(self):
        """
        Test the error for a script that does not exist.
        """
        result = self.run_pyftrace(['no_such_script.py'])

        self.assertIn("does not exist", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_no_target(self):
        """
        Test the error for a command line without a script or module.
        """
        result = self.run_pyftrace(['--verbose'])

        self.assertIn("a script or -m module is required", result.stderr)
        self.assertEqual(result.returncode, 2)

    def test_traceback_of_program(self):
        """
        A program that dies of an exception leaves the traceback python
        would print for it, without the frames of pyftrace.
        """
        result = self.run_source("""
            def work():
                raise KeyError("missing")

            work()
        """)

        self.assertIn("Traceback (most recent call last):", result.stderr)
        self.assertIn("in work", result.stderr)
        self.assertIn("KeyError: 'missing'", result.stderr)
        self.assertNotIn("pyftrace", result.stderr.replace(self.script, ""))
        self.assertNotIn("runpy", result.stderr)
        self.assertEqual(result.returncode, 1)

    @unittest.skipIf(sys.platform == "win32", "sends SIGINT")
    def test_interrupted_program(self):
        """
        Ctrl-C ends the program as it does without pyftrace: its own
        traceback, the report if one was asked for, death by SIGINT.
        """
        directory = tempfile.mkdtemp(prefix="pyftrace-test-")
        self.addCleanup(shutil.rmtree, directory, True)
        script = os.path.join(directory, "script.py")
        with open(script, "w") as f:
            f.write(textwrap.dedent("""
                import time

                def wait():
                    print("waiting", flush=True)
                    time.sleep(30)

                wait()
            """))
        cmd = [self.python_executable, '-m', self.pyftrace_module, '-r', script]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   cwd=self.project_root,
                                   universal_newlines=True)
        while "waiting" not in process.stdout.readline():
            pass
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=20)

        self.assertIn("in wait", stderr)
        self.assertIn("KeyboardInterrupt", stderr)
        self.assertNotIn("runpy", stderr)
        self.assertRegex(stdout, r"wait\s+\|\s+\d+\.\d+ seconds\s+\|\s+1")
        self.assertEqual(-signal.SIGINT, process.returncode)

    def test_syntax_error_of_program(self):
        """
        A script that does not compile is reported like python does.
        """
        result = self.run_source("""
            def work(:
        """)

        self.assertIn("SyntaxError", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_negative_counts(self):
        """
        A negative number of lines or levels is refused, not taken as
        "print nothing".
        """
        for option in ('-n', '-d'):
            result = self.run_pyftrace([option, '-1', self.foobar_script])

            self.assertIn("is negative", result.stderr)
            self.assertEqual(result.returncode, 2)

    def test_script_options(self):
        """
        What follows the script belongs to the script, options that
        pyftrace has itself included.
        """
        result = self.run_source("""
            import sys

            def show():
                return sys.argv[1:]

            show()
        """, args=['-d', '1'],
             script_args=['-v', '--depth', '3', '-m', 'mod', '--help', 'x'])

        self.assertIn("Returning show-> ['-v', '--depth', '3', '-m', 'mod', "
                      "'--help', 'x']", result.stdout)
        self.assertEqual("", result.stderr)
        self.assertEqual(result.returncode, 0)

    def test_grouped_options(self):
        """
        The script is found behind grouped short options, attached
        values and abbreviated long options.
        """
        result = self.run_source("""
            import sys

            def show():
                return sys.argv[1:]

            show()
        """, args=['-ad', '1', '-n5', '--form', 'text', '--max-lines=5'],
             script_args=['-n', '0'])

        self.assertIn("Returning show-> ['-n', '0']", result.stdout)
        self.assertEqual(result.returncode, 0)

class RegressionTests(PyftraceTestCase):
    """
    Programs that used to be traced wrongly, or broken by being traced.
    """

    @unittest.skipUnless(hasattr(sys, "monitoring"), "needs sys.monitoring")
    def test_program_measures_coverage(self):
        """
        A program that runs a coverage tool on sys.monitoring finds the
        tool id of coverage tools free.
        """
        result = self.run_source("""
            import sys

            def work():
                return 1

            monitoring = sys.monitoring
            monitoring.use_tool_id(monitoring.COVERAGE_ID, "coverage")
            work()
            monitoring.free_tool_id(monitoring.COVERAGE_ID)
        """)

        self.assertEqual("", result.stderr)
        self.assertEqual(["    Called work from line 9",
                          "    Returning work-> 1"],
                         self.trace_lines(result.stdout))

    def test_program_sets_profile_function(self):
        """
        A program that sets a profile function of its own gets its
        events, and the trace goes on during and after.
        """
        result = self.run_source("""
            import sys

            seen = []

            def profiler(frame, event, arg):
                if event == "call":
                    seen.append(frame.f_code.co_name)

            def work(n):
                return n

            sys.setprofile(profiler)
            work(1)
            mine = sys.getprofile() is profiler
            sys.setprofile(None)
            work(2)
            print("profiler saw", seen, mine, sys.getprofile())
        """)

        self.assertIn("profiler saw ['work'] True None", result.stdout)
        self.assertEqual(["    Called work from line 14",
                          "    Returning work-> 1",
                          "    Called work from line 17",
                          "    Returning work-> 2"],
                         self.trace_lines(result.stdout))

    def test_program_runs_cprofile(self):
        """
        The trace goes on after the program has profiled a part of
        itself with cProfile, and cProfile gets its numbers.
        """
        result = self.run_source("""
            import cProfile

            def work(n):
                return n

            profiler = cProfile.Profile()
            profiler.enable()
            work(1)
            profiler.disable()
            calls = [entry.callcount for entry in profiler.getstats()
                     if getattr(entry.code, "co_name", "") == "work"]
            print("cProfile counted", calls)
            work(2)
        """)

        self.assertIn("cProfile counted [1]", result.stdout)
        self.assertEqual(["    Called work from line 14",
                          "    Returning work-> 2"],
                         self.trace_lines(result.stdout)[-2:])

    def test_program_sets_thread_profile_function(self):
        """
        The same for threading.setprofile(): the threads started after
        it are both profiled by the program and traced.
        """
        result = self.run_source("""
            import threading

            seen = []

            def profiler(frame, event, arg):
                if event == "call":
                    seen.append(frame.f_code.co_name)

            def work():
                return 1

            def start():
                thread = threading.Thread(target=work)
                thread.start()
                thread.join()

            threading.setprofile(profiler)
            start()
            threading.setprofile(None)
            start()
            print("profiler saw work:", seen.count("work"))
        """)

        self.assertIn("profiler saw work: 1", result.stdout)
        self.assertEqual(2, result.stdout.count("Returning work-> 1"))

    def test_generator_resumed_by_exception(self):
        """
        A generator that is resumed by throw() or close() is traced
        like one resumed by next().
        """
        result = self.run_source("""
            def helper(tag):
                return tag

            def gen():
                try:
                    yield helper("first")
                except ValueError:
                    yield helper("recovered")
                finally:
                    helper("cleanup")

            g = gen()
            next(g)
            g.throw(ValueError("x"))
            g.close()
        """)

        lines = [line.split("->")[0] for line in self.trace_lines(result.stdout)]
        self.assertEqual([
            "    Called gen from line 14",
            "        Called helper from line 7",
            "        Returning helper",
            "    Returning gen",
            "    Called gen from line 15",
            "        Called helper from line 9",
            "        Returning helper",
            "    Returning gen",
            "    Called gen from line 16",
            "        Called helper from line 11",
            "        Returning helper",
            "    Raised gen",
        ], lines)

    def test_coroutine_resumed_by_exception(self):
        """
        A coroutine whose await fails goes on in the trace: what it
        does about the exception is the interesting part.
        """
        result = self.run_source("""
            import asyncio

            def helper(tag):
                return tag

            async def fail():
                await asyncio.sleep(0)
                raise KeyError("missing")

            async def main():
                try:
                    await asyncio.ensure_future(fail())
                except KeyError:
                    return helper("handled")

            asyncio.run(main())
        """)

        lines = self.trace_lines(result.stdout)
        self.assertEqual([
            "        Called helper from line 15",
            "        Returning helper-> handled",
            "    Returning main-> handled",
        ], lines[-3:])
        self.assertRegex(lines[-4], r"^    Called main from line \d+$")

    def test_library_code_not_traced(self):
        """
        Test that standard library and generated code is left out.
        """
        result = self.run_source("""
            import json
            import os
            from collections import namedtuple

            Point = namedtuple("Point", "x y")

            def name_of(path):
                json.dumps({"path": path})
                Point(1, 2)
                return os.path.basename(path)

            name_of("a/b.txt")
        """)

        self.assertEqual([
            "    Called name_of from line 13",
            "    Returning name_of-> b.txt",
        ], self.trace_lines(result.stdout))

    def test_verbose_leaves_out_standard_library(self):
        """
        -v adds built-ins and installed packages, not the standard
        library, on every version of Python.  Before, Python 3.8 to 3.11
        traced it, the import system included.
        """
        result = self.run_source("""
            import json

            def main():
                import csv
                return len(json.dumps([1]))

            main()
        """, args=['-v'])

        self.assertEqual([
            "    Called main from line 8",
            "        Called len from line 6",
            "        Returning len",
            "    Returning main-> 3",
        ], self.trace_lines(result.stdout))

    def test_class_body_not_traced(self):
        """
        Test that defining a class is not shown as a call.
        """
        result = self.run_source("""
            class Greeter:
                greeting = "hi"

                def hello(self):
                    return self.greeting

            Greeter().hello()
        """)

        self.assertEqual([
            "    Called hello from line 8",
            "    Returning hello-> hi",
        ], self.trace_lines(result.stdout))

    def test_repr_of_callable_not_called(self):
        """
        Test that naming a callable does not run its __repr__.
        """
        result = self.run_source("""
            class Greeter:
                def __repr__(self):
                    raise RuntimeError("repr must not be called")

                def __call__(self):
                    return "hi"

            Greeter()()
            print("still alive")
        """)

        self.assertIn("still alive", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_unprintable_return_value(self):
        """
        Test that a return value whose __str__ raises does no harm.
        """
        result = self.run_source("""
            class Broken:
                def __str__(self):
                    raise RuntimeError("no str for you")

            def make():
                return Broken()

            make()
            print("still alive")
        """)

        self.assertEqual([
            "    Called make from line 9",
            "    Returning make-> <unprintable Broken>",
        ], self.trace_lines(result.stdout))
        self.assertIn("still alive", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_long_value_on_one_line(self):
        """
        Test that a long or multi-line value is cut down to one line.
        """
        result = self.run_source("""
            def table():
                return "row 1\\nrow 2\\nrow 3"

            def big():
                return list(range(500))

            table()
            big()
        """)
        lines = self.trace_lines(result.stdout)

        self.assertEqual(4, len(lines))
        self.assertEqual("    Returning table-> row 1 row 2 row 3", lines[1])
        self.assertTrue(lines[3].endswith("..."))
        self.assertLess(len(lines[3]), 250)

    def test_decorated_function(self):
        """
        Test that a function wrapped with functools.wraps returns properly.
        """
        result = self.run_source("""
            import functools

            def logged(func):
                @functools.wraps(func)
                def wrapper(*args):
                    return func(*args)
                return wrapper

            @logged
            def add(a, b):
                return a + b

            def after():
                return 1

            add(1, 2)
            after()
        """)
        lines = self.trace_lines(result.stdout)

        # The decorator itself is called from line 10 or 11, depending on
        # the Python version
        self.assertEqual([
            "    Called wrapper from line 17",
            "        Called add from line 7",
            "        Returning add-> 3",
            "    Returning wrapper-> 3",
            "    Called after from line 18",
            "    Returning after-> 1",
        ], lines[2:])

    def test_coroutine(self):
        """
        Test that a suspended coroutine is not taken for one that raised.
        """
        result = self.run_source("""
            import asyncio

            async def fetch():
                await asyncio.sleep(0)
                return "data"

            async def broken():
                await asyncio.sleep(0)
                raise ValueError("v")

            asyncio.run(fetch())
            try:
                asyncio.run(broken())
            except ValueError:
                pass
        """)
        lines = [re.sub(r" from line \d+", "", line).strip()
                 for line in self.trace_lines(result.stdout)]

        self.assertEqual([
            "Called fetch", "Returning fetch-> None",
            "Called fetch", "Returning fetch-> data",
            "Called broken", "Returning broken-> None",
            "Called broken", "Raised broken",
        ], lines)

    def test_exception_detail(self):
        """
        Test that the sys.monitoring engine names the exception.
        """
        if sys.version_info < (3, 12):
            self.skipTest("sys.setprofile does not report the exception")
        result = self.run_pyftrace(['--argument', self.exception_script])

        self.assertIn("Raised parse-> ValueError: invalid literal for int() "
                      "with base 10: 'x'", result.stdout)
        self.assertIn("Called parse (text='x') from line 5", result.stdout)

    def test_script_is_main_module(self):
        """
        Test that the script runs as __main__, so that it can be pickled.
        """
        result = self.run_source("""
            import pickle
            import sys

            def work():
                return 1

            assert sys.modules["__main__"].work is work
            assert pickle.loads(pickle.dumps(work)) is work
            print("pickled")
        """)

        self.assertIn("pickled", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_hard_exit_keeps_trace(self):
        """
        Test that the trace survives a program that ends with os._exit().
        """
        result = self.run_source("""
            import os

            def crash():
                os._exit(7)

            crash()
        """)

        self.assertEqual(["    Called crash from line 7"],
                         self.trace_lines(result.stdout))
        self.assertEqual(result.returncode, 7)

class LibraryCodeTests(unittest.TestCase):
    """
    Which files count as the program's own code.
    """

    def setUp(self):
        self.tracer = get_tracer()
        self.verbose_tracer = get_tracer(verbose=True)
        self.project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..'))

    def test_user_code(self):
        script = os.path.join(self.project_root, 'examples', 'foobar.py')
        self.assertTrue(self.tracer.should_trace(script))

    def test_standard_library(self):
        self.assertFalse(self.tracer.should_trace(os.__file__))
        self.assertFalse(self.verbose_tracer.should_trace(os.__file__))
        # The same file reached through a resolved path
        self.assertFalse(self.tracer.should_trace(os.path.realpath(os.__file__)))

    def test_site_dir_above_standard_library(self):
        """
        On Windows, outside a virtual environment, the installation
        directory that holds the standard library is a site directory.
        """
        stdlib = sysconfig.get_paths()["stdlib"]
        install_dir = os.path.dirname(stdlib)
        original = site.getsitepackages
        site.getsitepackages = lambda: [install_dir]
        try:
            tracer = get_tracer(verbose=True)
        finally:
            site.getsitepackages = original
        self.assertFalse(tracer.should_trace(os.__file__))

    def test_run_by_import_system(self):
        """
        A finder that a library adds to the import system, and what it
        calls, run for the import system.  The same function called by
        the program, and the body of a module, do not.
        """
        site_dir = os.path.join(tempfile.gettempdir(), "pyftrace-site")
        self.verbose_tracer.site_dirs = self.verbose_tracer.normalize_dirs(
            [site_dir])
        frames = {}
        namespace = {"frames": frames, "sys": sys}

        def define(source, file_name):
            exec(compile(textwrap.dedent(source), file_name, "exec"),
                 namespace)

        define("""
            def hook():
                frames["hook"] = sys._getframe()
            def finder():
                hook()
        """, os.path.join(site_dir, "library.py"))
        define("""
            def find_spec():
                finder()
        """, "<frozen importlib._bootstrap>")
        define("""
            def program():
                finder()
        """, os.path.join(self.project_root, "program.py"))
        define("""
            frames["body"] = sys._getframe()
        """, os.path.join(site_dir, "module.py"))

        namespace["find_spec"]()
        self.assertTrue(self.verbose_tracer.run_by_import_system(frames["hook"]))
        namespace["program"]()
        self.assertFalse(self.verbose_tracer.run_by_import_system(frames["hook"]))
        self.assertFalse(self.verbose_tracer.run_by_import_system(frames["body"]))

    def test_site_packages(self):
        module = os.path.join(sysconfig.get_paths()["purelib"],
                              "somepackage", "module.py")
        self.assertFalse(self.tracer.should_trace(module))
        # Third-party code is what --verbose adds
        self.assertTrue(self.verbose_tracer.should_trace(module))

    def test_sibling_of_library_directory(self):
        # A directory is not library code for sharing a prefix with one
        stdlib = sysconfig.get_paths()["stdlib"]
        self.assertFalse(self.tracer.is_stdlib_code(stdlib + "-mine/module.py"))

    def test_code_without_source_file(self):
        for name in ("<string>", "<frozen posixpath>",
                     os.path.abspath("<string>")):
            self.assertFalse(self.tracer.should_trace(name), name)
        self.assertTrue(self.tracer.is_stdlib_code("<frozen posixpath>"))

    def test_tracer_code(self):
        import pyftrace.tracer
        self.assertFalse(self.tracer.should_trace(pyftrace.tracer.__file__))
        self.assertFalse(self.verbose_tracer.should_trace(pyftrace.tracer.__file__))

    def test_file_filters(self):
        examples = os.path.join(self.project_root, 'examples')
        script = os.path.join(examples, 'foobar.py')
        other = os.path.join(examples, 'module_trace', 'module_a.py')

        self.assertTrue(self.tracer.file_selected(script))
        self.tracer.file_filter = normalize_patterns(
            [os.path.join(examples, 'module_trace')])
        self.assertFalse(self.tracer.file_selected(script))
        self.assertTrue(self.tracer.file_selected(other))
        self.tracer.file_filter = ()
        self.tracer.file_exclude = normalize_patterns(
            [os.path.join(examples, '*', 'module_a.py')])
        self.assertTrue(self.tracer.file_selected(script))
        self.assertFalse(self.tracer.file_selected(other))

try:
    import curses
    import pty
except ImportError:
    pty = None

@unittest.skipUnless(pty, "needs a pseudo-terminal and curses")
class TuiTests(PyftraceTestCase):
    """
    The TUI, driven through a pseudo-terminal.
    """

    def run_tui(self, args, wait_for):
        """
        Start 'pyftrace tui', wait until the screen shows wait_for, quit
        with 'q' and return what was drawn and the exit status.
        """
        command = [self.python_executable, '-m', self.pyftrace_module] + args
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.project_root)
            os.environ.update(TERM="xterm", LINES="40", COLUMNS="160",
                              PYTHONPATH=self.python_path())
            os.execv(command[0], command)

        drawn = b""
        quit_sent = False
        deadline = time.time() + 30
        while time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    data = b""
                if not data:
                    break       # the terminal is gone: the TUI has exited
                drawn += data
            if not quit_sent and wait_for.encode() in drawn:
                os.write(fd, b"q")
                quit_sent = True
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        # Take the cursor movements out of what is left on the screen
        text = re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][A-Z0-9]|\x1b[=>]",
                      b"\n", drawn).decode("utf-8", "replace")
        return [line.strip() for line in text.splitlines()], status

    def test_tui(self):
        """
        Test that the TUI shows the trace in its short form and quits.
        """
        lines, status = self.run_tui(['tui', self.foobar_script],
                                     "Returning foo")

        self.assertEqual(0, status)
        for expected in ("Called foo", "Called bar", "Returning bar",
                         "Returning foo"):
            self.assertIn(expected, lines)

    def test_tui_raised(self):
        """
        Test that the TUI shortens a 'Raised' line like the others.
        """
        lines, status = self.run_tui(['--path', 'tui', self.exception_script],
                                     "Raised load")

        self.assertEqual(0, status)
        # Without the exception and the path, which belong in the detail pane
        self.assertIn("Raised parse", lines)
        self.assertIn("Raised load", lines)

class ConcurrencyTests(PyftraceTestCase):
    """
    Threads and child processes.
    """

    def test_thread_outlives_script(self):
        """
        Test that a thread is traced after the script has run to its end.
        """
        result = self.run_source("""
            import threading
            import time

            def done():
                return "done"

            def late():
                time.sleep(0.2)
                return done()

            threading.Thread(target=late).start()
        """)
        lines = [re.sub(r" from line \d+", "", line)
                 for line in self.trace_lines(result.stdout)]

        self.assertEqual([
            "[tid N]     Called late",
            "[tid N]         Called done",
            "[tid N]         Returning done-> done",
            "[tid N]     Returning late-> done",
        ], lines)

    def test_thread_json(self):
        """
        Test that '--format json' carries the thread id as a field.
        """
        args = ['--format', 'json', self.threads_script]
        result = self.run_pyftrace(args)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        tids = {event.get("tid") for event in events if "depth" in event}

        # The main thread has none, the worker thread has a number
        self.assertEqual(2, len(tids))
        self.assertIn(None, tids)
        self.assertTrue(all(isinstance(event["tid"], int)
                            for event in events if "tid" in event))

    @unittest.skipUnless(hasattr(os, "fork"), "os.fork() is not available")
    def test_fork(self):
        """
        Test that a forked process is traced under its own pid.
        """
        result = self.run_source("""
            import os

            def child_work():
                return "child"

            def parent_work():
                return "parent"

            def main():
                pid = os.fork()
                if pid == 0:
                    child_work()
                    os._exit(0)
                os.waitpid(pid, 0)
                return parent_work()

            main()
        """)

        self.assertEqual([
            "    Called main from line 18",
            "[pid N]     Called child_work from line 13",
            "[pid N]     Returning child_work-> child",
            "        Called parent_work from line 16",
            "        Returning parent_work-> parent",
            "    Returning main-> parent",
        ], self.trace_lines(result.stdout))

    POOL_SCRIPT = """
        import multiprocessing

        def square(n):
            return n * n

        def main():
            with multiprocessing.Pool(2) as pool:
                return pool.map(square, [1, 2, 3])

        if __name__ == "__main__":
            main()
    """

    def test_pool(self):
        """
        Test that the function a multiprocessing pool runs is traced.
        """
        result = self.run_source(self.POOL_SCRIPT)
        lines = [re.sub(r" from line \d+", "", line)
                 for line in self.trace_lines(result.stdout)]

        self.assertEqual(3, lines.count("[pid N]     Called square"))
        for value in (1, 4, 9):
            self.assertIn(f"[pid N]     Returning square-> {value}", lines)
        self.assertEqual(result.returncode, 0)

    def test_pool_report(self):
        """
        Test that '--report' includes pool workers, which are killed.
        """
        result = self.run_source(self.POOL_SCRIPT,
                                 ['--report', '--format', 'json'])
        rows = self.report_calls(result)

        self.assertEqual(3, rows["square"]["calls"])
        self.assertEqual("", result.stderr)

class CollapserTests(unittest.TestCase):
    """
    The folding of repeated calls, on trace events directly.
    """

    @staticmethod
    def call(depth, name, children=(), returns=True):
        events = [{"event": "call", "depth": depth, "function": name}]
        for child in children:
            events += child
        if returns:
            events.append({"event": "return", "depth": depth, "function": name})
        return events

    @staticmethod
    def collapse(events):
        output = []
        collapser = Collapser(output.append)
        for event in events:
            collapser.feed(event)
        collapser.finish()
        return output

    @staticmethod
    def expand(output):
        """
        Undo the folding: a repeat event stands for copies of the call
        right before it.
        """
        events = []
        for event in output:
            if event["event"] != "repeat":
                events.append(event)
                continue
            start = len(events) - 1
            while not (events[start]["event"] == "call"
                       and events[start]["depth"] == event["depth"]):
                start -= 1
            events.extend(events[start:] * event["count"])
        return events

    def test_repeat(self):
        call = self.call
        events = call(1, "run", [call(2, "tick")] * 5)

        self.assertEqual(
            call(1, "run", [call(2, "tick"),
                            [{"event": "repeat", "depth": 2, "count": 4}]]),
            self.collapse(events))

    def test_different_calls_are_kept(self):
        call = self.call
        events = call(1, "run", [call(2, "a"), call(2, "b"), call(2, "a")])

        self.assertEqual(events, self.collapse(events))

    def test_repeat_at_top_level(self):
        events = self.call(1, "tick") * 3

        self.assertEqual(
            self.call(1, "tick") + [{"event": "repeat", "depth": 1, "count": 2}],
            self.collapse(events))

    def test_partial_repeat_is_released(self):
        call = self.call
        # The second call starts like the first but goes on differently
        first = call(2, "step", [call(3, "a"), call(3, "b")])
        second = call(2, "step", [call(3, "a"), call(3, "c")])
        events = call(1, "run", [first, second])

        self.assertEqual(events, self.collapse(events))

    def test_unfinished_trace(self):
        call = self.call
        # The program ends in the middle of a call that looked like a repeat
        events = call(1, "run", [call(2, "tick"), call(2, "tick"),
                                 call(2, "tick", returns=False)],
                      returns=False)

        self.assertEqual(events, self.expand(self.collapse(events)))
        self.assertEqual(events[-1], self.collapse(events)[-1])

    def test_long_call_is_not_held_back(self):
        call = self.call
        children = [call(2, f"step{number}")
                    for number in range(Collapser.MAX_EVENTS)]
        events = call(1, "big", children) * 2

        self.assertEqual(events, self.collapse(events))

    def random_calls(self, depth, rng, budget):
        events = []
        template = None
        for _ in range(rng.choice([0, 1, 2, 3, 5])):
            if budget[0] <= 0:
                break
            budget[0] -= 1
            if template is not None and rng.random() < 0.6:
                events.extend(template)
                continue
            children = []
            if depth < 5:
                children = [self.random_calls(depth + 1, rng, budget)]
            template = self.call(depth, rng.choice("abc"), children)
            template[-1]["event"] = rng.choice(["return", "return", "raise"])
            events.extend(template)
        return events

    def test_folding_loses_nothing(self):
        """
        Test on random call trees that expanding the folded trace gives
        back the original, also when the trace is cut off in the middle.
        """
        rng = random.Random(1)
        folded = 0
        for trial in range(500):
            events = self.random_calls(1, rng, [rng.choice([5, 20, 80, 400])])
            if rng.random() < 0.2 and len(events) > 2:
                events = events[:rng.randrange(1, len(events))]
            output = self.collapse(events)
            self.assertEqual(events, self.expand(output), f"trial {trial}")
            folded += len(events) - len(output)
        self.assertGreater(folded, 0)

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
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        print("\nPASS")
