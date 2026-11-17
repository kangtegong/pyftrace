import sys
import argparse
from .tracer import get_tracer
from .utils import find_module_file, normalize_patterns
from .output import FORMATS
from .tui import run_tui
from . import __version__
import tempfile
import os

def split_module_args(argv):
    """
    Split argv at '-m <module>'.  Like python itself, stop parsing
    options there: the rest of the command line belongs to the module.
    """
    for i, arg in enumerate(argv[:-1]):
        if arg == '--':
            break
        if arg == '-m':
            return argv[:i], argv[i + 1], argv[i + 2:]
    return argv, None, []

def run_target(tracer, module, script_path, target_args):
    if module:
        tracer.run_python_module(module, target_args)
    else:
        tracer.run_python_script(script_path, target_args)

def main():
    if sys.version_info < (3, 8):
        print("This tracer requires Python 3.8 or higher.")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        usage="%(prog)s [options] [tui] (script | -m module) [args ...]",
        description="pyftrace: Python function tracing tool.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('-V', '--version', action='version', version=f'pyftrace version {__version__}', help="Show the version of pyftrace and exit")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable built-in and third-party function tracing")
    parser.add_argument('-p', '--path', action='store_true', help="Show file paths in tracing output")
    parser.add_argument('-r', '--report', action='store_true', help="Generate a report of function execution times")
    parser.add_argument('-d', '--depth', type=int, help="Limit the tracing output to DEPTH")
    parser.add_argument('-n', '--max-lines', type=int, metavar='LINES', help="Stop printing the trace after LINES lines. The program keeps running")
    parser.add_argument('-c', '--collapse', action='store_true', help="Print a call that repeats the one before it only once, followed by a repeat count")
    parser.add_argument('-f', '--function', action='append', help="Trace only calls of <function> and its subcalls. Can be repeated")
    parser.add_argument('-e', '--exclude-function', action='append', help="Exclude calls of <function> (and its subcalls) from tracing. Can be repeated")
    parser.add_argument('-F', '--file', action='append', metavar='PATH', help="Trace only functions defined in PATH: a file, a directory or a glob. Can be repeated")
    parser.add_argument('-E', '--exclude-file', action='append', metavar='PATH', help="Do not trace functions defined in PATH. Can be repeated")
    parser.add_argument('-a', '--argument', action='store_true', help="Show function arguments in tracing output (Python frames only)")
    parser.add_argument('--format', choices=sorted(FORMATS), default='text', help="Output format: 'text' (default) or 'json', one JSON object per line")
    parser.add_argument('-o', '--output', help="Write tracing output to a file. The traced program's own output is not redirected")

    parser.add_argument('-m', dest='module', metavar='MODULE', help="Run and trace a library module as a script, like 'python -m'.\nEverything after MODULE is passed to the module.")

    parser.add_argument('script', nargs='*', help="Path to the script to run and trace. Specify 'tui' before the script path to run in TUI mode.")

    argv, module, module_args = split_module_args(sys.argv[1:])
    args = parser.parse_args(argv)

    is_tui_mode = bool(args.script) and args.script[0] == 'tui'
    targets = args.script[1:] if is_tui_mode else args.script
    script_path = None

    if module:
        if targets:
            parser.error("a script cannot be combined with -m")
        target_args = module_args
        # As 'python -m' does, look the module up from the current directory
        sys.path.insert(0, os.getcwd())
        if find_module_file(module) is None:
            print(f"Error: No module named '{module}'.")
            sys.exit(1)
    else:
        if not targets:
            parser.error("a script or -m module is required")
        script_path = targets[0]
        target_args = targets[1:]
        if not os.path.isfile(script_path):
            print(f"Error: Script '{script_path}' does not exist.")
            sys.exit(1)

    tracer_depth = args.depth if args.depth is not None else None
    func_filter = args.function 
    func_exclude = args.exclude_function

    output_stream = sys.stdout
    output_file_handle = None
    if args.output:
        # Child processes append to the same file, so the writes of this
        # process must go to its end too.  Empty it first.
        open(args.output, "w").close()
        output_file_handle = open(args.output, "a", buffering=1,
                                  encoding="utf-8")
        output_stream = output_file_handle

    try:
        if is_tui_mode:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
                temp_file_path = temp_file.name

            try:
                with open(temp_file_path, "a", buffering=1) as f:
                    tracer = get_tracer(
                        verbose=args.verbose,
                        show_path=args.path,
                        report_mode=False,
                        output_stream=f,
                        function_filter=func_filter,
                        function_exclude=func_exclude,
                        trace_arguments=args.argument
                    )
                    tracer.output_path = temp_file_path
                    tracer.max_depth = tracer_depth
                    tracer.max_lines = args.max_lines
                    tracer.collapse = args.collapse
                    tracer.file_filter = normalize_patterns(args.file)
                    tracer.file_exclude = normalize_patterns(args.exclude_file)
                    run_target(tracer, module, script_path, target_args)
                run_tui(temp_file_path)

            finally:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
        else:
            tracer = get_tracer(
                verbose=args.verbose,
                show_path=args.path,
                report_mode=args.report,
                output_stream=output_stream,
                function_filter=func_filter,
                function_exclude=func_exclude,
                trace_arguments=args.argument
            )
            tracer.output_path = args.output
            tracer.max_depth = tracer_depth
            tracer.max_lines = args.max_lines
            tracer.collapse = args.collapse
            tracer.file_filter = normalize_patterns(args.file)
            tracer.file_exclude = normalize_patterns(args.exclude_file)
            tracer.format = FORMATS[args.format]
            run_target(tracer, module, script_path, target_args)

            if args.report:
                tracer.print_report(stream=output_stream)
                sys.exit(0)
    finally:
        if output_file_handle:
            output_file_handle.close()

if __name__ == "__main__":
    main()

