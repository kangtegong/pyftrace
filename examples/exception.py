def parse(text):
    return int(text)

def load(text):
    return parse(text) + 1

def safe_load(text):
    try:
        return load(text)
    except ValueError:
        return -1

safe_load("1")
safe_load("x")
