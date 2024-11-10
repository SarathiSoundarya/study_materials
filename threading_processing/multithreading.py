# When to use Multi Threading
# I/O-bound tasks: Tasks that spend more time waiting for I/O operations (e.g., file operations, network requests).
#  Concurrent execution: When you want to improve the throughput of your application by performing multiple operations concurrently.
import threading
import time

def print_numbers():
    for i in range(5):
        time.sleep(2)
        print(f"number: {i}")

def print_letters():
    for letter in "abcde":
        time.sleep(2)
        print(f"letter: {letter}")

#define the threads
t1=threading.Thread(target=print_numbers)
t2=threading.Thread(target=print_letters)

#start the time
st=time.time()
print("time: ",st)

#start the threads
print("starting")
t1.start()
t2.start()

#wait for the thread to finish
t1.join()
t2.join()

print(time.time())
print("Time: ", time.time()-st)
## Multithreading
# When to use Multi Threading
##I/O-bound tasks: Tasks that spend more time waiting for I/O operations (e.g., file operations, network requests).
##  Concurrent execution: When you want to improve the throughput of your application by performing multiple operations concurrently.

