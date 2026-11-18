def tick():
    return "tock"

def run(count):
    for _ in range(count):
        tick()

run(1000)
