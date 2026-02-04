# Week 1 Learnings

## Lab 1.1 - Memory Experiments

- **Question:** Why does list(range()) use more memory than range()?

- **Hypothesis:** list(range()) creates a list of 10,000,000 integers in memory at once, while range() creates a generator expression that generates integers on the fly.

- **Experiment:** Tested both methods and memory usage, using tracemalloc() and getsizeof() to measure memory usage.

- **Results:** range() uses significantly less memory than list(range()), as expected.
getsizeof() returns the size of the object in memory, and it only gives the size of the object, not the nested objects inside, that is why it is dangerous to use it for memory analysis of complex/nested objects while tracemalloc() returns the memory usage of the program.

| Experiment | Input Size | Peak Memory (MB) | Object Size (MB) |
|---|---|---|---|
| list(range) | 10,000,000 | 381.46 | 76.29 |
| range | 10,000,000 | 0.0001 | ~0.00 |

![Benchmarks png file](../benchmarks/Lab_1.1_Memory_Benchmarks.png)

- **Explanation:** range() is an iterable expression, gives an iterator only, which calculates values in the runtime, storing only 3 values start, stop, and step, while list(range()) creates a list of 10,000,000 integers in memory at once, or meterializes all the values in the memory.

- **Real World Impact:** in our RAG pipeline, we will be ingesting and processing large volumes of documents and datasets, using generators and iterators will be very efficient in terms of memory management, as compared to using traditional approaches, reading complete files at once, which creates a risk of OOM ( out of memory) errors.

- **Example Scenerio:** Why can't I just use list(range()) to generate IDs?

- **Answer:** explained above very clearly. it becomes a problem when we have to generate millions of IDs, in that case it will consume a lot of memory, and will lead to OOM errors. Use generators and iterators instead.

## Lab 1.2 - Memory Leak Experiments

- **Question:** What are circular references and garbage collection, how does it affect memory, how leak is created?

- **Hypothesis:** when two objects reference each other, and if we remove the roots(variables in stack), the objects will not be garbage collected, because they are still referenced by each other, and it will lead to a memory leak. this will create orphan objects, essentially, memory leaks.

- **Experiment:** 

1- Created circular references using a class Leak, with a reference to the next object in the list, and the last object has a reference to the first object in the list.
2- Disabled garbage collector to prevent it from collecting the objects.
3- Measured memory usage before and after creating the leaks.
4- Deleted the leaks and measured memory usage again.
5- Enabled garbage collector and collected garbage.
6- Measured memory usage again.
7- Created benchmarks and saved them to a file.

- **Results:** 

| Metric | Before GC (Leaked) | After GC (Cleaned) |
|---|---|---|
| Current Memory (MB) | 122.07 | 0.00 |
| Peak Memory (MB) | 130.12 | 130.12 |
| Leaked Objects Count | 1,000,000 | 0 |

![Benchmarks png file](../benchmarks/Lab_1.2_memory_leak_benchmarks.png)


- **Explanation:** Circular references create memory leaks because the objects are still referenced by each other, so reference counting alone does not work. We need to use garbage collection to collect the garbage. This is why we see current memory as 122.07 MB, even after the list with leaked objects has been deleted

- **Real World Impact:** in our RAG pipeline, we will be processing large volumes of data, and if we create circular references, it will lead to memory leaks, and will cause OOM errors. We should avoid creating circular references, and if we do, we should use gc.collect() to collect the garbage. This can be a reason of silent production crashes

