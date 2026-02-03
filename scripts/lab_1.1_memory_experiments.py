import tracemalloc
from sys import getsizeof

#start measuring memory usage
tracemalloc.start()

# create large list of integers using range
my_list = list(range(10000000))

# get memory usage - current, peak using .get_traced_memory()
current_memory_1, peak_memory_1 = tracemalloc.get_traced_memory()

print(f'\n -- LAB 1.1 MEMORY EXPERIMENTS -- \n')

# print memory usage in MB
print(f'\n--- using list(range(10000000)) ---\n')
print(f"Current memory: {current_memory_1 / 1024 / 1024} MB")
print(f"Peak memory: {peak_memory_1 / 1024 / 1024} MB")
print(f'getsizeof(my_list): {getsizeof(my_list)} bytes , {getsizeof(my_list)/1024/1024} MB')
# stop measuring memory usage
tracemalloc.stop()

# -----------------

# using range()

tracemalloc.start()

my_range = range(10000000)

current_memory_2, peak_memory_2 = tracemalloc.get_traced_memory()

print(f'\n--- using range(10000000) ---\n')
print(f"Current memory: {current_memory_2 / 1024 / 1024} MB, {current_memory_2} bytes")
print(f"Peak memory: {peak_memory_2 / 1024 / 1024} MB, {peak_memory_2} bytes")
print(f'getsizeof(my_range): {getsizeof(my_range)} bytes , {getsizeof(my_range)/1024/1024} MB')
tracemalloc.stop()

print(f'\n --- COMPARISON ---\n')
print(f'\nlist(range(10000000)) current memory: {current_memory_1} bytes, {current_memory_1 / 1024 / 1024} MB')
print(f'\nrange(10000000) current memory: {current_memory_2} bytes, {current_memory_2 / 1024 / 1024} MB')
print(f'\nlist(range(10000000)) peak memory: {peak_memory_1} bytes, {peak_memory_1 / 1024 / 1024} MB')
print(f'\nrange(10000000) peak memory: {peak_memory_2} bytes, {peak_memory_2 / 1024 / 1024} MB')
print(f'\ndifference (peak) : {peak_memory_1 - peak_memory_2} bytes, {(peak_memory_1 - peak_memory_2) / 1024 / 1024} MB')
print(f'\nlist(range(10000000)) size: {getsizeof(my_list)} bytes , {getsizeof(my_list)/1024/1024} MB')
print(f'\nrange(10000000) size: {getsizeof(my_range)} bytes , {getsizeof(my_range)/1024/1024} MB')

print('\n' + '-' * 20)
print(f'for experiment using 100_000 (underscore syntax)')
tracemalloc.start()

my_list_2 = list(range(100_000))

current_memory_3, peak_memory_3 = tracemalloc.get_traced_memory()

print(f'\n--- using list(range(100_000)) ---\n')
print(f"Current memory(using list(range(100_000))): {current_memory_3 / 1024 / 1024} MB, {current_memory_3} bytes")
print(f"Peak memory(using list(range(100_000))): {peak_memory_3 / 1024 / 1024} MB, {peak_memory_3} bytes")

print(f'getsizeof(my_list_2): {getsizeof(my_list_2)} bytes, {getsizeof(my_list_2)/1024/1024} MB')

tracemalloc.stop()