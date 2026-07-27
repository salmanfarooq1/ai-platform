import sys
import tracemalloc
import gc
import uuid
import os
import json


class Leak:
    def __init__(self,id):
        self.id = id
        self.ref = None

        self.data = 'xyz' *1000


def create_leaks(num_objects):
    leaks_list = [Leak(i) for i in range(num_objects)]

    for i in range(num_objects-1):
        leaks_list[i].ref = leaks_list[i+1]
    leaks_list[-1].ref = leaks_list[0]

    return leaks_list

# Disable garbage collector so that we can measure the leaks

print(f' \n-- 1 - Measuring memory impact of circular references -- \n')

gc.disable()

# Start memory measurments

tracemalloc.start()

# get current memory usage

current_initial, peak_initial = tracemalloc.get_traced_memory()

print(f' -- Before creating leaks -- \n')

print(f'current memory usage: {current_initial / 1024} KB, {current_initial / 1024/ 1024} MB')
print(f'peak memory usage: {peak_initial / 1024} KB, {peak_initial / 1024/ 1024} MB')

# Create leaks

num_leak_objects = 1000000

leaks_list = create_leaks(num_leak_objects)

# Delete leaks

del leaks_list

# get current memory usage

current_final, peak_final = tracemalloc.get_traced_memory()

print(f'\n -- After creating ({num_leak_objects}) leaks and deleting them -- \n')

print(f'current memory usage: {current_final / 1024} KB, {current_final / 1024/ 1024} MB')
print(f'peak memory usage: {peak_final / 1024} KB, {peak_final / 1024/ 1024} MB')

found_leaks = sum(1 for obj in gc.get_objects() if isinstance(obj, Leak))
print(f'Number of leaks : {found_leaks}')

print(f'\n -- Reason for memory leak -- \n')

print(f'\n The memory leak is caused by the circular reference between the objects in the leaks_list. The objects are created in a way that each object has a reference to the next object in the list, and the last object has a reference to the first object in the list. This creates a cycle and it is now a memory leak')

print(f'\n -- 2- Solution (enabling gc and gc.collect()) -- \n')

# Enable  the garbage collector

gc.enable()

# Collect garbage

collected_garbage = gc.collect()

print(f'Number of objects collected by garbage collector: {collected_garbage}')

# get current memory usage

current_final_gc, peak_final_gc = tracemalloc.get_traced_memory()

print(f'\n -- After enabling garbage collector and collecting garbage -- \n')

print(f'current memory usage: {current_final_gc / 1024} KB, {current_final_gc / 1024/ 1024} MB')
print(f'peak memory usage: {peak_final_gc / 1024} KB, {peak_final_gc / 1024/ 1024} MB')

found_leaks_gc = sum(1 for obj in gc.get_objects() if isinstance(obj, Leak))
print(f'Number of leaks : {found_leaks_gc}')

print(f'\n -- 3- Benchmarking (Before and after) -- \n')

benchmarks = {
    'before_gc': {
        'current_memory': f'{current_final / 1024 / 1024:.2f} MB',
        'peak_memory': f'{peak_final / 1024 / 1024:.2f} MB',
        'leaks': found_leaks
    },
    'after_gc': {
        'current_memory': f'{current_final_gc / 1024 / 1024:.2f} MB',
        'peak_memory': f'{peak_final_gc / 1024 / 1024:.2f} MB',
        'leaks': found_leaks_gc
    }
}

output_path =  '/home/ubuntu/ai-platform/benchmarks/lab_1.2_memory_leak_benchmarks.json'
try:
    with open (output_path, 'w') as f:
        json.dump(benchmarks, f, indent=4)
    print(f'Benchmarks saved to {output_path}')
except FileNotFoundError:
    print(f'Creating directory {os.path.dirname(output_path)}')
    os.makedirs('benchmarks')
    with open (output_path, 'w') as f:
        json.dump(benchmarks, f, indent=4)
    print(f'Benchmarks saved to {output_path}')

