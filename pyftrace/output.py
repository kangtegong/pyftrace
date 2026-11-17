import json

INDENT = "    "

def format_text(event):
    """
    Render a trace event as a line of the classic pyftrace output.
    """
    kind = event["event"]
    indent = INDENT * event.get("depth", 0)

    if kind == "call":
        function = event["function"]
        caller = f"from line {event['line']}"
        if "defined_at" in event:
            function = f"{function}@{event['defined_at']}"
        if "caller_file" in event:
            caller = f"from {event['caller_file']}:{event['line']}"
        if "args" in event:
            function = f"{function} ({event['args']})"
        return f"{indent}Called {function} {caller}"

    if kind in ("return", "raise"):
        text = f"Returning {event['function']}"
        if kind == "raise":
            text = f"Raised {event['function']}"
        if "value" in event:
            text = f"{text}-> {event['value']}"
        if "exception" in event:
            text = f"{text}-> {event['exception']}"
        if "file" in event:
            text = f"{text} @ {event['file']}"
        return f"{indent}{text}"

    if kind == "start":
        if "module" in event:
            return f"Running module: {event['module']}"
        return f"Running script: {event['script']}"

    if kind == "truncated":
        return f"... trace truncated after {event['max_lines']} lines"

    if kind == "report":
        return (f"{event['function']:<15}\t| {event['seconds']:.6f} seconds"
                f"\t| {event['calls']}")

    raise ValueError(f"unknown trace event: {kind}")

def format_json(event):
    """
    Render a trace event as one JSON object per line.
    """
    return json.dumps(event, ensure_ascii=False)

FORMATS = {
    "text": format_text,
    "json": format_json,
}
