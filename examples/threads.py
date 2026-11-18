import threading

def square(n):
    return n * n

def worker(n):
    return square(n)

def main():
    thread = threading.Thread(target=worker, args=(3,))
    thread.start()
    thread.join()
    return square(4)

main()
