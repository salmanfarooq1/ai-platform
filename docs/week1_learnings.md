# Week 1 Learnings

## Lab 1.1 - Memory Experiments

- Question: Why does list(range()) use more memory than range()?

- Hypothesis: list(range()) creates a list of 10,000,000 integers in memory at once, while range() creates a generator expression that generates integers on the fly.

- Experiment: Tested both methods and memory usage, using tracemalloc() and getsizeof() to measure memory usage.

- Results: range() uses significantly less memory than list(range()), as expected.
getsizeof() returns the size of the object in memory, and it only gives the size of the object, not the nested objects inside, that is why it is dangerous to use it for memory analysis of complex/nested objects while tracemalloc() returns the memory usage of the program.

| Experiment | Input Size | Peak Memory (MB) | Object Size (MB) |
|---|---|---|---|
| list(range) | 10,000,000 | 381.46 | 76.29 |
| range | 10,000,000 | 0.0001 | ~0.00 |

- Explanation: range() is an iterable expression, gives an iterator only, which calculates values in the runtime, storing only 3 values start, stop, and step, while list(range()) creates a list of 10,000,000 integers in memory at once, or meterializes all the values in the memory.

- Real World Impact: in our RAG pipeline, we will be ingesting and processing large volumes of documents and datasets, using generators and iterators will be very efficient in terms of memory management, as compared to using traditional approaches, reading complete files at once, which creates a risk of OOM ( out of memory) errors.

- Example Scenerio: Why can't I just use list(range()) to generate IDs?

- Answer: explained above very clearly. it becomes a problem when we have to generate millions of IDs, in that case it will consume a lot of memory, and will lead to OOM errors. Use generators and iterators instead.