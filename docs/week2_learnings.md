## Lab 2.1: Event Loop Deep Dive

**Question:**
Is AsyncIO single-threaded or multi-threaded? Is it parallel or concurrent? Why does async/await exist?

**Hypothesis:**
As of my theoretical knowledge, asyncio is praimarily for utilizing the time that is otherwise wasted during I/O operations. and it may come out as 'fast' but it is not actually, iy just uses time more efiiciently and it is concurrent but not parallel.

**Experiment:**
- Created 10 async tasks
- Each prints threading.current_thread()
- Used asyncio.gather() to run concurrently
- Used eventloop-blocking funtions like time.sleep() to prove that they should be never used in async code as they block the event loop. It also proves that asyncio is single-threaded. 

**Results:**
| Task ID | Thread Name | 
|---------|-------------|
| 0-9     | MainThread  |

**Explanation:**
- from the very first experiment we proved that asyncio is single-threaded, by printing the thread used by each task, and each task used the same thread, even when running concurrently. This proves single threading and concurrency both at the same time.
when we hit await, it acts as yield, and pauses, and gives conrol back to event loop, so it can continue running other tasks and does not wait or block. It is greatly differentiable when we are dealing with input output tasks, or featching urls, or doing something that causes the event loop to wait for something. The event loop knows about which tasks are ready to run using epoll, select, kqueue, etc. Deep under the hood, OS timer comes into play to wake up the event loop when it is time to run the next task.

**Real-World Impact:**
In production, this means 1,000 embedding requests won't create 1,000 threads. 
They'll all execute on ONE thread, switching during I/O waits. This would greatly improve the speed and efficiency of the application.