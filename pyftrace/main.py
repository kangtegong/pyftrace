import sys
import argparse
from .tracer import get_tracer
from .tui import run_tui
from . import __version__
import tempfile
import os

def main():
    if sys.version_info < (3, 8):
        print("This tracer requires Python 3.8 or higher.")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        usage="%(prog)s [options] [tui] script [script_args ...]",
        description="pyftrace: Python function tracing tool.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('-V', '--version', action='version', version=f'pyftrace version {__version__}', help="Show the version of pyftrace and exit")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable built-in and third-party function tracing")
    parser.add_argument('-p', '--path', action='store_true', help="Show file paths in tracing output")
    parser.add_argument('-r', '--report', action='store_true', help="Generate a report of function execution times")
    parser.add_argument('-d', '--depth', type=int, default=0, help="Set the maximum tracing depth")

    parser.add_argument('script', nargs='+', help="Path to the script to run and trace. Specify 'tui' before the script path to run in TUI mode.")

    args = parser.parse_args()

    is_tui_mode = False
    script_path = None
    script_args = []

    if args.script[0] == 'tui':
        is_tui_mode = True
        if len(args.script) < 2:
            print("Error: Please specify a script to run in TUI mode.")
            sys.exit(1)
        script_path = args.script[1]
        script_args = args.script[2:]
    else:
        script_path = args.script[0]
        script_args = args.script[1:]

    if not os.path.isfile(script_path):
        print(f"Error: Script '{script_path}' does not exist.")
        sys.exit(1)

    if is_tui_mode:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, "w") as f:
                tracer = get_tracer(verbose=args.verbose, show_path=args.path, report_mode=False, output_stream=f, max_depth=args.depth)
                tracer.run_python_script(script_path, script_args)
            run_tui(temp_file_path)

        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    else:
        tracer = get_tracer(verbose=args.verbose, show_path=args.path, report_mode=args.report, max_depth=args.depth)
        tracer.run_python_script(script_path, script_args)

        if args.report:
            tracer.print_report()
            sys.exit(0)

if __name__ == "__main__":
    main()

