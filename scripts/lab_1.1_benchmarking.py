import tracemalloc
from sys import getsizeof
import os
import json

# Input Configuration

input_config = [10000, 100000, 1000000]

# Define functions to test

def use_range(n):
    return range(n)

def use_list(n):
    return list(range(n))

# Define function to measure memory usage

def measure_memory(func, n):
    # start memory tracking
    tracemalloc.start()
    # call the function
    result_object = func(n)
    # get memory usage
    current_memory, peak_memory = tracemalloc.get_traced_memory()
    # stop memory tracking
    tracemalloc.stop()

    return current_memory, peak_memory, getsizeof(result_object)

# Benchmarking loop

output_buffer = []
if not os.path.exists('benchmarks'):
    os.makedirs('benchmarks')
output_path = f'benchmarks/lab_1.1_benchmarking.json'

for n in input_config:
    current_memory_range    , peak_memory_range, object_size_range = measure_memory(use_range, n)
    current_memory_list, peak_memory_list, object_size_list = measure_memory(use_list, n)
    output_buffer.append({
        'input': n,
        'range': {'current_memory_bytes': current_memory_range, 'peak_memory_bytes': peak_memory_range, 'object_size_bytes': object_size_range},
        'list': {'current_memory_bytes': current_memory_list, 'peak_memory_bytes': peak_memory_list, 'object_size_bytes': object_size_list}
    })
try:
    with open(output_path, 'w') as f:
        json.dump(output_buffer, f, indent=4)
    print(f'Benchmarking results saved to {output_path}')
except Exception as e:
    print(f'Error: {e}')

