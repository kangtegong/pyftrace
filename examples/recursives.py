def countdown(n):
    if n <= 0:
        print("Countdown finished!")
    else:
        print(f"Counting down: {n}")
        countdown(n - 1) 

countdown(50)

