import multiprocessing
import math
import sys
import time
sys.set_int_max_str_digits(100000)

def compute_factorial(num):
    print(f"computing factorial of {num}")
    result=math.factorial(num)
    print(f"factorial for {num} is {result}")
    return result

if __name__=="__main__":
    numbers=[5000, 6000, 7000, 8000]
    st=time.time()
    with multiprocessing.Pool() as pool:
        results=pool.map(compute_factorial, numbers)
    
    print(f"Time:{time.time()-st}")
    print(f"Results:{results}")