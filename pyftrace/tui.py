import curses
import sys
import re
# import logging
import os
import platform

def run_tui(trace_file_path):
    if not os.path.isfile(trace_file_path):
        print(f"Trace file '{trace_file_path}' does not exist.")
        sys.exit(1)

    with open(trace_file_path, 'r') as f:
        trace_lines = f.readlines()

    curses.wrapper(tui_main, trace_lines)

def tui_main(stdscr, trace_lines):
    # logging.basicConfig(filename='tui_debug.log', level=logging.DEBUG,
    #                     format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        # Initialize
        curses.curs_set(0)  # Hide cursor
        curses.noecho()     # Do not display input characters on screen
        curses.cbreak()     # Process key input immediately
        stdscr.keypad(True) # Allow special key input

        if not curses.has_colors():
            curses.endwin()
            print("Terminal does not support colors.")
            sys.exit(1)

        curses.start_color()
        curses.use_default_colors()

        # Check if terminal supports 256 colors
        supports_256_colors = False
        if curses.COLORS >= 256:
            supports_256_colors = True

        # Initialize color pairs
        if supports_256_colors:
            try:
                curses.init_pair(1, curses.COLOR_WHITE, 236)    # Gray for background (256-color)
                curses.init_pair(2, curses.COLOR_YELLOW, 236)   # Highlight selected line (256-color)
                curses.init_pair(3, curses.COLOR_WHITE, 236)    # Normal line color (256-color)
                curses.init_pair(4, curses.COLOR_GREEN, 236)    # Function Detail text (256-color)
                curses.init_pair(5, curses.COLOR_BLUE, 236)     # Instruction text (256-color)
            except curses.error as e:
                # logging.error(f"Error initializing 256-color pairs: {e}")
                supports_256_colors = False

        if not supports_256_colors:
            # Initialize color pairs for 8-color mode
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)   # White-black for background
            curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Yellow-black for selected line
            curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)   # White-black for normal line
            curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Green-black for Function Detail text
            curses.init_pair(5, curses.COLOR_BLUE, curses.COLOR_BLACK)    # Blue-black for Instruction text

        BG_COLOR = curses.color_pair(1)
        HIGHLIGHT_COLOR = curses.color_pair(2)
        NORMAL_COLOR = curses.color_pair(3)
        DETAIL_COLOR = curses.color_pair(4)
        INSTRUCTION_COLOR = curses.color_pair(5)

        height, width = stdscr.getmaxyx()

        # Check minimum terminal size
        min_height = 20
        min_width = 60
        if height < min_height or width < min_width:
            curses.endwin()
            print(f"Terminal size is too small. Minimum size: {min_width}x{min_height}")
            sys.exit(1)

        # Set window size and position
        display_height = height - 12  # Leave enough space
        display_width = width - 2
        display_window = curses.newwin(display_height, display_width, 1, 1)

        stdscr.bkgd(' ', BG_COLOR)
        display_window.bkgd(' ', BG_COLOR)
        stdscr.clear()
        stdscr.border()

        # Set up Function Detail window
        detail_window = curses.newwin(6, width - 4, height - 8, 2)
        detail_window.bkgd(' ', BG_COLOR)
        detail_window.border()
        detail_window.addstr(0, 2, " Function Detail ", DETAIL_COLOR | curses.A_BOLD)
        detail_window.refresh()

        # Add instruction text (just above the bottom)
        instruction_text = "↑/↓: Scroll | PgUp/PgDn: Page Scroll | Home/End: Jump | ←/→: Horizontal Scroll | q: Quit"
        # Truncate text if it exceeds the window width
        max_instruction_length = width - 4  # 1 margin on each side
        if len(instruction_text) > max_instruction_length:
            # Add '...' to indicate truncation
            instruction_text = instruction_text[:max_instruction_length - 3] + "..."

        # Draw instruction_text directly on stdscr at height -2 with background color
        stdscr.attron(INSTRUCTION_COLOR | curses.A_BOLD)
        try:
            stdscr.addnstr(height - 2, 1, instruction_text.ljust(width - 2), width - 2)
        except curses.error:
            pass
        stdscr.attroff(INSTRUCTION_COLOR | curses.A_BOLD)
        stdscr.refresh()

        # Refresh windows
        display_window.refresh()
        detail_window.refresh()

        current_line = 0
        max_line = len(trace_lines)
        selected_line = 0
        previous_selected_line = -1  # Initial value to ensure first selection updates

        current_col = 0  # Horizontal scroll offset


        def parse_trace_line(line):
            is_windows = platform.system() == 'Windows'

            if is_windows:
                # for windows
                call_match = re.match(
                    r'(?P<indent>\s*)Called\s+(?P<func_name>[<>?\w]+)'
                    r'\s*@\s*(?P<def_path>.+?)(?::(?P<def_line>\d+))?'
                    r'\s+from\s+(?P<call_path>.+?):(?P<call_line>\d+)',
                    line
                )
                return_match = re.match(
                    r'(?P<indent>\s*)Returning\s+(?P<func_name>[<>?\w]+)'
                    r'(?:\s*->\s*(?P<retval>[^@]+))?'
                    r'(?:\s*@\s*(?P<file_path>.+))?$',
                    line
                )
            else:
                # for macOS, Linux
                call_match = re.match(
                    r'(?P<indent>\s*)Called\s+(?P<func_name>[<>?\w]+)'
                    r'\s*@\s*(?P<def_path>[^:]+)(?::(?P<def_line>\d+))?'
                    r'\s+from\s+(?P<call_path>[^:]+):(?P<call_line>\d+)',
                    line
                )
                return_match = re.match(
                    r'(?P<indent>\s*)Returning\s+(?P<func_name>[<>?\w]+)'
                    r'(?:\s*->\s*(?P<retval>[^@]+))?'
                    r'(?:\s*@\s*(?P<file_path>[^@]+))?$',
                    line
                )

            if call_match:
                func_name = call_match.group("func_name")
                def_path = call_match.group("def_path") if call_match.group("def_path") else ""
                def_line = call_match.group("def_line") if call_match.group("def_line") else ""
                call_path = call_match.group("call_path")
                call_line = call_match.group("call_line")

                return {
                    "type": "call",
                    "func_name": func_name,
                    "def_path": def_path,
                    "def_line": def_line,
                    "call_path": call_path,
                    "call_line": call_line,
                }
            elif return_match:
                func_name = return_match.group("func_name")
                retval = return_match.group("retval").strip() if return_match.group("retval") else ""
                file_path = return_match.group("file_path").strip() if return_match.group("file_path") else ""


                return {
                    "type": "return",
                    "func_name": func_name,
                    "retval": retval,
                    "file_path": file_path,
                }
            else:
                # logging.warning(f"Failed to parse line: '{line}'")
                pass
            return None

        def simplify_trace_line(line):
            """
            Simplify trace lines to 'Called {function}' or 'Returning {function}' format.
            Keep indentation and remove '@' and any following information.
            """
            call_match = re.match(r'(?P<indent>\s*)Called\s+(?P<func_name>[<>?\w]+)', line)
            return_match = re.match(r'(?P<indent>\s*)Returning\s+(?P<func_name>[<>?\w]+)', line)

            if call_match:
                indent = call_match.group('indent')
                func_name = call_match.group('func_name')
                return f"{indent}Called {func_name}"
            elif return_match:
                indent = return_match.group('indent')
                func_name = return_match.group('func_name')
                return f"{indent}Returning {func_name}"
            else:
                return line  # Return original line if it cannot be simplified

        # Precompute simplified lines for performance
        simplified_lines = [simplify_trace_line(line.rstrip('\n')) for line in trace_lines]

        while True:
            # Update display window
            display_window.erase()
            for idx in range(display_height):
                line_num = current_line + idx
                if line_num >= max_line:
                    break
                line = simplified_lines[line_num]
                # Apply horizontal scrolling
                if current_col < len(line):
                    visible_line = line[current_col:current_col + display_width]
                else:
                    visible_line = ''

                # Ensure the string fits within the window width
                if len(visible_line) > display_width:
                    visible_line = visible_line[:display_width]
                elif len(visible_line) < display_width:
                    visible_line = visible_line.ljust(display_width)

                try:
                    if line_num == selected_line:
                        display_window.addnstr(idx, 0, visible_line, display_width, HIGHLIGHT_COLOR)
                    else:
                        display_window.addnstr(idx, 0, visible_line, display_width, NORMAL_COLOR)
                except curses.error:
                    pass

            display_window.noutrefresh()

            # Update detail window only if the selected line has changed
            if selected_line != previous_selected_line:
                detail_window.erase()
                detail_window.border()
                detail_window.addstr(0, 2, " Function Detail ", DETAIL_COLOR | curses.A_BOLD)
                selected_text = trace_lines[selected_line].strip()

                parsed_data = parse_trace_line(selected_text)
                if parsed_data:
                    if parsed_data["type"] == "call":
                        func_name = parsed_data['func_name']
                        def_path = parsed_data['def_path']
                        def_line = parsed_data['def_line']
                        call_path = parsed_data['call_path']
                        call_line = parsed_data['call_line']

                        detail_window.addstr(1, 2, f"[ Function Name ] {func_name}", DETAIL_COLOR)
                        if def_path == "built-in":
                            detail_window.addstr(2, 2, f"[ Defined Path:Line ] built-in", DETAIL_COLOR)
                        else:
                            detail_window.addstr(2, 2, f"[ Defined Path:Line ] {def_path}:{def_line}", DETAIL_COLOR)
                        detail_window.addstr(3, 2, f"[ Called Path:Line ] {call_path}:{call_line}", DETAIL_COLOR)
                    elif parsed_data["type"] == "return":
                        func_name = parsed_data['func_name']
                        retval = parsed_data['retval']
                        file_path = parsed_data.get('file_path', '')

                        detail_window.addstr(1, 2, f"[ Function Name ] {func_name}", DETAIL_COLOR)
                        # Do not display retval if it's a built-in function
                        if retval:
                            detail_window.addstr(2, 2, f"[ Return Value ] {retval}", DETAIL_COLOR)
                        if file_path:
                            detail_window.addstr(3, 2, f"[ Returned From ] {file_path}", DETAIL_COLOR)
                        else:
                            detail_window.addstr(3, 2, f"[ Returned From ] built-in", DETAIL_COLOR)
                else:
                    detail_window.addstr(1, 2, "No detailed information available.", DETAIL_COLOR)

                detail_window.noutrefresh()
                previous_selected_line = selected_line

            curses.doupdate()

            key = stdscr.getch()

            if key == curses.KEY_UP:
                if selected_line > 0:
                    selected_line -= 1
                    # Scroll up if necessary
                    if selected_line < current_line:
                        current_line -= 1
            elif key == curses.KEY_DOWN:
                if selected_line < max_line - 1:
                    selected_line += 1
                    # Scroll down if necessary
                    if selected_line >= current_line + display_height:
                        current_line += 1
            elif key == curses.KEY_PPAGE:  # Page Up
                if selected_line > 0:
                    selected_line = max(0, selected_line - display_height)
                    current_line = max(0, current_line - display_height)
            elif key == curses.KEY_NPAGE:  # Page Down
                if selected_line < max_line - 1:
                    selected_line = min(max_line - 1, selected_line + display_height)
                    current_line = min(max_line - display_height, current_line + display_height)
            elif key == curses.KEY_HOME:  # Home
                selected_line = 0
                current_line = 0
            elif key == curses.KEY_END:  # End
                selected_line = max_line - 1
                current_line = max_line - display_height
                if current_line < 0:
                    current_line = 0
            elif key == curses.KEY_LEFT:
                if current_col > 0:
                    current_col -= 5  # Adjust scroll unit
                    if current_col < 0:
                        current_col = 0
            elif key == curses.KEY_RIGHT:
                # Set scroll limit based on length of the longest line
                max_line_length = max(len(line) for line in simplified_lines)
                if current_col + display_width < max_line_length:
                    current_col += 5  # Adjust scroll unit
            elif key == ord('q') or key == ord('Q'):
                break

    finally:
        # Restore settings upon program exit
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()

