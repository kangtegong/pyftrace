import unittest
import subprocess
import sys
import os
import re

class PyftraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Set up  test env.
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
        Test '-v'
        """
        result = self.run_pyftrace(['-v'])
        self.assertIn("pyftrace version 0.1.0", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_version_flag_long_version(self):
        """
        Test  '--version'
        """
        result = self.run_pyftrace(['--version'])
        self.assertIn("pyftrace version 0.1.0", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_help_option_short_h(self):
        """
        Test '-h'
        """
        result = self.run_pyftrace(['-h'])
        self.assertIn("usage:", result.stdout)
        self.assertIn("pyftrace: Python function call tracing tool.", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_help_option_long_help(self):
        """
        Test '--help'
        """
        result = self.run_pyftrace(['--help'])
        self.assertIn("usage:", result.stdout)
        self.assertIn("pyftrace: Python function call tracing tool.", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_tracing_script_default(self):
        """
        Test basic tracing
        """
        args = [self.main_script]
        result = self.run_pyftrace(args)

        expected_output = \
f"""Running script: {self.main_script}
Called main from line 10
    Called function_a from line 5
Function A is called.
        Returning function_a-> Result from function A
    Called function_b from line 6
Function B is called.
        Returning function_b-> Result from function B
Results: Result from function A, Result from function B
    Returning main-> None
Returning <module>-> None"""

        expected_output = expected_output.replace('\r\n', '\n').strip()
        actual_output = result.stdout.replace('\r\n', '\n').strip()

        self.assertIn(expected_output, actual_output)
        self.assertEqual(result.returncode, 0)

    def test_tracing_script_verbose(self):
        """
        Test '--verbose'
        """
        args = [self.main_script, '--verbose']
        result = self.run_pyftrace(args)

        expected_output = \
f"""Running script: {self.main_script}
Called main from line 10
    Called function_a from line 5
        Called print from line 2
Function A is called.
            Returning print
        Returning function_a-> Result from function A
    Called function_b from line 6
        Called print from line 2
Function B is called.
            Returning print
        Returning function_b-> Result from function B
    Called print from line 7
Results: Result from function A, Result from function B
        Returning print
    Returning main-> None
Returning <module>-> None"""

        expected_output = expected_output.replace('\r\n', '\n').strip()
        actual_output = result.stdout.replace('\r\n', '\n').strip()

        self.assertIn(expected_output, actual_output)
        self.assertEqual(result.returncode, 0)

    def test_tracing_script_path(self):
        """
        Test '--path'
        """
        args = [self.main_script, '--path']
        result = self.run_pyftrace(args)

        expected_output = \
f"""Running script: {self.main_script}
Called main@{self.main_script}:4 from {self.main_script}:10
    Called function_a@{self.module_a}:1 from {self.main_script}:5
Function A is called.
        Returning function_a-> Result from function A @ {self.module_a}
    Called function_b@{self.module_b}:1 from {self.main_script}:6
Function B is called.
        Returning function_b-> Result from function B @ {self.module_b}
Results: Result from function A, Result from function B
    Returning main-> None @ {self.main_script}
Returning <module>-> None @ {self.main_script}"""

        expected_output = expected_output.replace('\r\n', '\n').strip()
        actual_output = result.stdout.replace('\r\n', '\n').strip()

        self.assertIn(expected_output, actual_output)
        self.assertEqual(result.returncode, 0)

def test_tracing_script_report(self):
    """
    Test '--report'
    """
    args = [self.main_script, '--report']
    result = self.run_pyftrace(args)

    # regex pattern: any floating-point number in the tim e field
    expected_output_pattern = \
rf"""Running script: {re.escape(self.main_script)}
Function A is called.
Function B is called.
Results: Result from function A, Result from function B

Function Name\t\|\s+Total Execution Time\s+\|\s+Call Count
-+\nmain\s+\|\s+[0-9]+\.[0-9]+ seconds\s+\|\s+1
function_a\s+\|\s+[0-9]+\.[0-9]+ seconds\s+\|\s+1
function_b\s+\|\s+[0-9]+\.[0-9]+ seconds\s+\|\s+1"""

    actual_output = result.stdout.replace('\r\n', '\n').strip()

    self.assertRegex(actual_output, expected_output_pattern)
    self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.TestLoader().loadTestsFromTestCase(PyftraceTests))
    if result.wasSuccessful():
        print("\nPASS")

