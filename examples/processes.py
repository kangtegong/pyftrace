import multiprocessing

def square(n):
    return n * n

def worker(n):
    return square(n)

def main():
    process = multiprocessing.Process(target=worker, args=(3,))
    process.start()
    process.join()
    return square(4)

if __name__ == "__main__":
    main()
