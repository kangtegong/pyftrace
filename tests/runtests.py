import unittest
import subprocess
import sys
import os
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pyftrace import __version__ as pyftrace_version

class PyftraceTests(unittest.TestCase):
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
        return result

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

        # Expected output without tracing 'print' in default mode
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

        # Normalize line endings and strip trailing whitespace
        expected_output = expected_output.replace('\r\n', '\n').strip()
        actual_output = result.stdout.replace('\r\n', '\n').strip()

        # Compare the expected output with actual output
        self.assertIn(expected_output, actual_output)
        self.assertEqual(result.returncode, 0)

    def test_tracing_script_verbose(self):
        """
        Test '--verbose' flag for detailed tracing.
        """
        args = [self.main_script, '--verbose']
        result = self.run_pyftrace(args)

        # Expected output with tracing 'print' in verbose mode
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

        # Normalize line endings and strip trailing whitespace
        expected_output = expected_output.replace('\r\n', '\n').strip()
        actual_output = result.stdout.replace('\r\n', '\n').strip()

        # Compare the expected output with actual output
        self.assertIn(expected_output, actual_output)
        self.assertEqual(result.returncode, 0)

    def test_tracing_script_path(self):
        """
        Test '--path' flag for tracing with file paths.
        """
        args = [self.main_script, '--path']
        result = self.run_pyftrace(args)

        # Adjusted expected line numbers based on actual output
        # Verify the actual line numbers in your scripts and adjust accordingly
        expected_output = f"""Running script: {self.main_script}
Called main@{self.main_script}:4 from {self.main_script}:10
    Called function_a@{self.module_a}:1 from {self.main_script}:5
Function A is called.
    Returning function_a-> ret_a @ {self.module_a}
    Called function_b@{self.module_b}:1 from {self.main_script}:6
Function B is called.
    Returning function_b-> ret_b @ {self.module_b}
Results: ret_a, ret_b
Returning main-> None @ {self.main_script}"""

        # Normalize line endings and strip trailing whitespace
        expected_output = expected_output.replace('\r\n', '\n').strip()
        actual_output = result.stdout.replace('\r\n', '\n').strip()

        # Compare the expected output with actual output
        self.assertIn(expected_output, actual_output)
        self.assertEqual(result.returncode, 0)


#     def test_tracing_script_report(self):
#         """
#         Test '--report' flag for generating execution reports.
#         """
#         args = [self.main_script, '--report']
#         result = self.run_pyftrace(args)

#         # Define the expected run output section
#         expected_run_output = f"""Running script: {self.main_script}
# Function A is called.
# Function B is called.
# Results: ret_a, ret_b"""

#         # Define regex pattern for the report section
#         report_header = r"Function Name\s+\|\s+Total Execution Time\s+\|\s+Call Count"
#         report_separator = r"-+"
#         report_entries = [
#             r"main\s+\|\s+\d+\.\d+ seconds\s+\|\s+1",
#             r"function_a\s+\|\s+\d+\.\d+ seconds\s+\|\s+1",
#             r"function_b\s+\|\s+\d+\.\d+ seconds\s+\|\s+1",
#         ]

#         # Combine the report section into a single regex pattern
#         report_pattern = (
#             report_header + r"\n" +
#             report_separator + r"\n" +
#             "\n".join(report_entries)
#         )

#         # Combine the entire expected output regex
#         expected_output_pattern = (
#             re.escape(expected_run_output) +
#             r"\n\n" +
#             report_pattern
#         )

#         # Normalize line endings and strip trailing whitespace
#         actual_output = result.stdout.replace('\r\n', '\n').strip()

#         # Remove any leading/trailing whitespace in expected pattern
#         expected_output_pattern = expected_output_pattern.strip()

#         # Use re.DOTALL to allow multi-line matching
#         self.assertRegex(actual_output, expected_output_pattern)
#         self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.TestLoader().loadTestsFromTestCase(PyftraceTests))
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        print("\nPASS")
