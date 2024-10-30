import sys
import argparse
from .tracer import Pyftrace
from . import __version__

def main():
    if sys.version_info < (3, 12):
        print("This tracer requires Python 3.12 or higher.")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description=(
            "pyftrace: Python function call tracing tool.\n\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument('-v', '--version', action='store_true', help="Show the version of pyftrace and exit")

    parser.add_argument('script', nargs='?', help="Path to the Python script to run and trace")
    parser.add_argument('-V', '--verbose',action='store_true', help="Enable built-in and third-party function tracing")
    parser.add_argument('-p', '--path', action='store_true', help="Show file paths in tracing output")
    parser.add_argument('-r', '--report', action='store_true', help="Generate a report of function execution times")

    args = parser.parse_args()

    if args.version:
        print(f"pyftrace version {__version__}")
        sys.exit(0)

    if not args.script:
        parser.print_help()
        sys.exit(1)

    tracer = Pyftrace(verbose=args.verbose, show_path=args.path)
    tracer.report_mode = args.report

    tracer.run_python_script(args.script)

    if tracer.report_mode:
        tracer.print_report()

if __name__ == "__main__":
    main()

