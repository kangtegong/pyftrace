import sys
import argparse
from .tracer import SimplePyftrace

def main():
    if sys.version_info < (3, 12):
        print("This tracer requires Python 3.12 or higher.")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description=(
            "Required Python version: 3.12+\n\n"
            "Usage:\n"
            "  $ pyftrace [options] <script>\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument('script', help="Path to the Python script to run and trace")
    parser.add_argument('--verbose', action='store_true', help="Enable built-in and third-party function tracing")
    parser.add_argument('--path', action='store_true', help="Show file paths in tracing output")
    parser.add_argument('--report', action='store_true', help="Generate a report of function execution counts & times")
    args = parser.parse_args()
    
    tracer = SimplePyftrace(verbose=args.verbose, show_path=args.path)
    tracer.report_mode = args.report
    
    tracer.run_python_script(args.script)
    
    if tracer.report_mode:
        tracer.print_report()

if __name__ == "__main__":
    main()

