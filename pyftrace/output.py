import errno
import json
import mmap
import os
import struct
import tempfile

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

INDENT = "    "

# The fields that tell which process and thread an event comes from.
# The process and the thread pyftrace was started in have neither.
ORIGIN_KEYS = ("pid", "tid")

def format_text(event):
    """
    Render a trace event as a line of the classic pyftrace output.
    """
    kind = event["event"]
    indent = INDENT * event.get("depth", 0)
    origin = [f"{key} {event[key]}" for key in ORIGIN_KEYS if key in event]
    if origin:
        indent = f"[{' '.join(origin)}] {indent}"

    if kind == "call":
        function = event["function"]
        caller = f"from line {event['line']}"
        if "defined_at" in event:
            function = f"{function}@{event['defined_at']}"
        if "caller_file" in event:
            caller = f"from {event['caller_file']}:{event['line']}"
        elif "caller_module" in event:
            caller = f"{caller} in {event['caller_module']}"
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

    if kind == "repeat":
        times = "time" if event["count"] == 1 else "times"
        return f"{indent}... repeated {event['count']} more {times}"

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

class LineCounter:
    """
    A number in a small file that every process of the traced program
    maps into its memory, so that --max-lines limits what all of them
    print together.

    The file is locked while a line is counted: two processes that
    print at the same moment must not both get the last line.
    """
    FORMAT = "q"

    def __init__(self, path=None):
        size = struct.calcsize(self.FORMAT)
        if path is None:
            fd, path = tempfile.mkstemp(prefix="pyftrace-lines-")
            os.write(fd, bytes(size))
        else:
            fd = os.open(path, os.O_RDWR)
        self.path = path
        self.fd = fd
        self.map = mmap.mmap(fd, size)

    @property
    def value(self):
        return struct.unpack_from(self.FORMAT, self.map)[0]

    def claim(self):
        """
        Count one more line and return its number.
        """
        self.lock()
        try:
            return self.increment()
        finally:
            self.unlock()

    def lock(self):
        if fcntl is not None:
            fcntl.lockf(self.fd, fcntl.LOCK_EX)
        elif msvcrt is not None:
            # Windows locks the bytes that follow the position of the file
            os.lseek(self.fd, 0, os.SEEK_SET)
            while True:
                try:
                    msvcrt.locking(self.fd, msvcrt.LK_LOCK, self.map.size())
                    return
                except OSError as error:
                    # LK_LOCK gives up after ten seconds of waiting.  Any
                    # other error would come back on every try.
                    if error.errno != errno.EDEADLOCK:
                        raise

    def unlock(self):
        if fcntl is not None:
            fcntl.lockf(self.fd, fcntl.LOCK_UN)
        elif msvcrt is not None:
            os.lseek(self.fd, 0, os.SEEK_SET)
            msvcrt.locking(self.fd, msvcrt.LK_UNLCK, self.map.size())

    def increment(self):
        value = self.value + 1
        struct.pack_into(self.FORMAT, self.map, 0, value)
        return value

    def remove(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

class Frame:
    """
    The state the Collapser keeps for one call that has not returned.
    """
    __slots__ = ("events", "previous", "count", "expected", "matched")

    def __init__(self, expected=None):
        # What this call has put out so far; None once it is too long
        self.events = []
        # The last finished call made from this one, and its repeat count
        self.previous = None
        self.count = 0
        # While this call still looks like a repeat of its predecessor,
        # the events of the predecessor and how many of them matched.
        self.expected = expected
        self.matched = 0

class Collapser:
    """
    Fold a call that repeats the previous call made from the same
    function, including everything below it, into a single 'repeat'
    event behind the first occurrence.

    The first occurrence is passed on as it happens.  A call that
    follows it is held back for as long as it produces the same events;
    it is dropped and counted if it does so to the end, and passed on
    from the point where it differs otherwise.
    """
    # Calls that put out more events than this are never folded
    MAX_EVENTS = 100

    def __init__(self, sink):
        self.sink = sink
        # frames[0] stands for the top level, frames[n] for depth n
        self.frames = [Frame()]

    def feed(self, event):
        kind = event["event"]
        depth = event.get("depth", 0)

        if kind == "call":
            self.drop_frames(depth)
            self.frames.append(Frame(self.frames[-1].previous))
            self.write(len(self.frames) - 1, event)
        elif kind in ("return", "raise") and depth < len(self.frames):
            self.drop_frames(depth + 1)
            if depth > 0:
                self.close(event)
        else:
            self.write(len(self.frames) - 1, event)

    def finish(self):
        """
        Put out what is still held back at the end of the trace.
        """
        for level in range(1, len(self.frames)):
            if self.frames[level].expected is not None:
                self.diverge(level)
        for level in reversed(range(len(self.frames))):
            self.flush_repeat(level)

    def drop_frames(self, count):
        """
        Forget calls whose exit was never seen, down to count frames.
        """
        while len(self.frames) > count:
            level = len(self.frames) - 1
            if self.frames[level].expected is not None:
                self.diverge(level)
            self.flush_repeat(level)
            self.frames.pop()
            self.frames[-1].previous = None

    def write(self, level, event):
        """
        Add an event to the output of the call at the given level and
        hand it up, unless that call is still being held back.
        """
        while level > 0:
            frame = self.frames[level]
            if frame.events is not None:
                frame.events.append(event)
                if len(frame.events) > self.MAX_EVENTS:
                    frame.events = None
            if frame.expected is not None:
                if (frame.matched < len(frame.expected)
                        and frame.expected[frame.matched] == event):
                    frame.matched += 1
                    return
                self.diverge(level)
            level -= 1
        self.sink(event)

    def diverge(self, level):
        """
        The call at this level is not a repeat after all: release the
        events held back for it.
        """
        frame = self.frames[level]
        parent = self.frames[level - 1]
        held = frame.expected[:frame.matched]
        frame.expected = None

        self.flush_repeat(level - 1)
        parent.previous = None
        for event in held:
            self.write(level - 1, event)

    def flush_repeat(self, level):
        frame = self.frames[level]
        if frame.count == 0:
            return
        event = {"event": "repeat", "depth": level + 1, "count": frame.count}
        first = frame.previous[0]
        event.update((key, first[key]) for key in ORIGIN_KEYS if key in first)
        frame.count = 0
        self.write(level, event)

    def close(self, event):
        level = len(self.frames) - 1
        frame = self.frames[level]
        self.flush_repeat(level)
        self.write(level, event)

        if (frame.expected is not None
                and frame.matched != len(frame.expected)):
            self.diverge(level)

        self.frames.pop()
        parent = self.frames[-1]
        if frame.expected is not None:
            parent.count += 1
        elif frame.events is not None:
            parent.previous = tuple(frame.events)
        else:
            parent.previous = None

FORMATS = {
    "text": format_text,
    "json": format_json,
}
