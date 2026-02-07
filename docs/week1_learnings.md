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

## Lab 1.3: File Chunk Iterator

**Question**
How can we process files larger than our available RAM without causing *Out of Memory (OOM)* errors? What is the impact of *"Eager Loading"* vs *"Lazy Loading"* on system resources?

**Hypothesis**
Reading a file using standard `f.read()` will consume memory proportional to the file size O(N),because it will load entire file in memory, and will cause OOM errors. Implementing a custom *Iterator pattern* with a fixed chunk size will allow us to process files of any size with constant memory usage O(1), as only one chunk exists in memory at a time.

---

**Experiment**
1.  *Data Generation:* Generated a *100MB dummy binary file* to simulate a large dataset.
2.  *Implementation:* Created a custom `FileChunkIterator` class supporting:
    - *Iteration Protocol:* `(__iter__, __next__)` to yield data in small chunks.
    - *Context Management:* `(__enter__, __exit__)` to ensure resource cleanup/file closing even on errors.
3.  *Test Scenarios:*
    - *Ad-hoc (The Hog):* Opens the file and reads all bytes into a single variable.
    - *Smart (The Iterator):* Uses the custom class to read the file in *1KB chunks*, discarding data after measurement.
4.  *Measurement:* Used `tracemalloc` to record Peak Memory usage for both approaches.

---

**Results**

| Metric | Ad-hoc (Read All) | Smart (Chunk Iterator) |
| :--- | :--- | :--- |
| **Peak Memory (MB)** | ~95.47 MB | ~0.007 MB (7.4 KB) |
| **Current Memory (MB)** | ~95.46 MB | ~0.0003 MB |
| **Efficiency Gain** | - | **~13,000x Lower Memory** |

---

**Explanation**
* **The "Ad-hoc" method:** Forces the OS to allocate a contiguous block of RAM to hold the entire 100MB file content. Memory usage scales linearly with file size. This mayb be fine for small files, but in large data pipelines, RAG, ingestions, it will definitely lead to OOM errors.
* **The "Smart" method:** Uses **Lazy Evaluation**. It only keeps a single chunk (1024 bytes) in memory at any given millisecond. As soon as the loop moves to the next iteration, the previous chunk is discarded and garbage collected, keeping the memory footprint flat regardless of file size. This way our pipeline is scalable, highly memory optimized and stable.

**Real World Impact**
In our **RAG (Retrieval-Augmented Generation) pipeline**, we process massive PDFs and continuous data streams. 
* **Risk:** If a worker attempts to load a 2GB PDF entirely into RAM to split it, it will crash (OOM). 
* **Solution:** Using this Iterator pattern ensures our pipeline is scalable and stable, allowing a 2GB RAM worker to process a 100GB file without breaking, crashing or throwing OOM errors. This is crucial for a smart, scalable and robust RAG pipeline.

## Lab 1.4: Generator Pipeline

**Question**
What if we need to process a large file that requires multiple steps as in a pipeline, using as less memory as we can? 

**Hypothesis**
Above single file reading concept can be expanded into multi-step pipeline, but instead of creating own iterator classes, we can use generators, and chain them together to create a pipeline.

---

**Experiment**
1.  *Data:* Used the existing 100MB dummy file from Lab 1.3
2.  *Implementation:* Implemented a generator pipeline using `read_chunks`, `clean_chunks` and `embed_chunks` functions. Each of these functions is a generator function, they use yield.
3.  *Test Scenarios:*
    - *Naive (The Hog):* Reads entire file at once, creates separate list for each step ( cleaning, chunking, embedding).
    - *Smart (The Generator Pipeline):* Uses the generator pipeline to read the file in *1KB chunks*, discarding data after measurement.
4.  *Measurement:* Used `tracemalloc` to record Peak Memory usage for both approaches.

---

**Results**

| Metric | Naive (The Hog) | Smart (Generator Pipeline) |
| :--- | :--- | :--- |
| **Peak Memory (MB)** | ~196.39 MB | ~0.04 MB (45.35 KB) |
| **Current Memory (MB)** | ~196.39 MB | ~ 0.01 MB (5.90 KB) |
| **Efficiency Gain** | - | **~4800x Lower Memory** |

---

**Explanation**
* **The "Naive" method:** Uses much more memory ( would crash for large files) as it creates multiple lists in memory, one for each step. This adds up, and can lead to OOM crashes
* **The "Smart" method:** Uses **Lazy Evaluation**. Efficiently chains multiple steps into a single pipeline where only one chunk is being processed at a time, which means there is only one chunk in the memory at one time, discarded after being processed (this can be stored in a database or a file, or sent to a queue, or processed in real time). This is a memory efficient way to process large files. 

**Real World Impact**
In our **RAG pipeline**, while processing massive PDFs and continous data streams, using generator based pipelines can process massive files with constant memory usage (O(1)), which is a lot more efficient and cost effective than using eager loading (O(N)).

## Lab 1.5: Production Module Architecture

**Problem**
We have scattered code in multiple files, essentially the scripts. The problem would definitely be much more visible when the codebase grows and we need to reuse the same functions in multiple places. 

**Challenge**
Transform isolated code into a production-ready Python package that others (including future me) can import and use.

---

**Architecture Decisions**

1. **Separation of Concerns**
   - `readers.py`: This file would contain all the file reading related functions, and classes. *FileChunkIterator* and *read_chunks* for now.
   - `processors.py`: Processing functions. *clean_chunks* for now.
   - `embedders.py`: Embedding functions. *embed_chunks* for now.
   - `__init__.py`: This file would contain the public API for the package, and essentially convert /ingestion folder into a module.

2. **Why This Structure?**

   - When I need to add PDFReader next week, I only touch `readers.py`. 
   - The processors and embedders won't care WHERE the chunks are coming from.
   
   - When I swap OpenAI embeddings for Cohere, I only touch `embedders.py`.
   - The readers and processors don't care HOW I create vectors.
   
   - This is **Separation of Concerns** - each module has ONE job:
   - readers: Get data IN
   - processors: Transform data
   - embedders: Create semantic representations


3. **Public API Design**
   - What we expose: `FileChunkIterator`, `read_chunks`, `clean_chunks`, `embed_chunks`
   - Why these specifically: `FileChunkIterator` and `read_chunks` are exposed as they would be used to read the file, and `clean_chunks` and `embed_chunks` are exposed as they would be used to process the file.

---

**Implementation**

**Directory Structure Created:**
```
core/
└── ingestion/
    ├── __init__.py       # __all__
    ├── readers.py        # FileChunkIterator and read_chunks
    ├── processors.py     # clean_chunks
    └── embedders.py      # embed_chunks
```

**Key Implementation Choices:**
- Absolute imports: Better readability, less chance of import errors. 
- One key consideration was about using both FileChunkIterator and read_chunks. FileChunkIterator is a class, and read_chunks is a function. I decided to expose both:
  - FileChunkIterator: as it is a class, can be better customized for future ( such as adding indexes etc.)
  - read_chunks: as it is a simpler generator function, can be quickly used without overhead.
  - Since I am thinking of it as Library, and Libraries provide OPTIONS!  

---

**Integration Test**

**Test File:** `scripts/lab_1.5_integration_test.py`

**What We Tested:**
1. Imports work correctly
2. Pipeline executes without errors
3. Output format is correct (128-dim embeddings)
4. Processes large file successfully

**Test Results:**
```
✓ Imports test PASSED
✓ Successfully processed 97,754 chunks
✓ Module integration test PASSED
```

**What This Proves:**
- Processing 97,754 chunks successfully proves:
1. Imports work across package boundaries - Python can find our module
2. Generators chain correctly - Data flows through the pipeline
3. Most importantly, someone else can now do
```python
from core.ingestion import read_chunks, clean_chunks
```

---

**Key Learnings**

1. **Module vs Script**
   - module is a package, can be imported anywhere in the code, and it provides a single source of truth.
   - script is simply a file, that requires code duplication if needed to be reused, and introduces maintanance overhead.

2. **The `__init__.py` Pattern**
   - It is a great way to control what is exposed to the public API.

3. **Import Errors I Hit** 
   - When I tried to import from `core.ingestion` and 
   got "ModuleNotFoundError", I realized Python doesn't magically know about my project structure.
   - So I added an empty __init__.py file to the core folder as well, and I ran *export PYTHONPATH=$PYTHONPATH:.* to fix, it is like explicitly telling python where to look for modules.
   - mostly in production, it is handeled automatically by package managers, but knowing the PATH fundamentals is important.

4. **Code Reusability**
   - Before Lab 1.5: Would need to copy paste code from scripts into other files.
   - After Lab 1.5: Can import the functions from the module. and this approach is much cleaner.

---

**Real-World Impact**

In production RAG systems:
- We would need to import multiple functions from multiple modules, we may need the file reading functionality in multiple places, or the chunking functionality, or the embedding functionality, or all of them.
- While we swap embedding model, we just need to go to the module and edit the function, even if it is imported and being used in multiple locations. Even better, we would have secret management for constants, which would further make code updates even more easier 
- This greatly helps while working in a team, as everyone can access all the resources in a single place, and work with that. this ensures zero ambiguity, or confusion.
