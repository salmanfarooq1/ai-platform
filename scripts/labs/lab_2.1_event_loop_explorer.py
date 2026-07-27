# lab_task- 2.1.1

# Print threading.current_thread() in 5 different async tasks
# Prove they're all the same thread

import threading, asyncio, time

#ddefine an async func, it will be used to get a coroutine obj, we put sleep(2) to simulate some work
async def print_thread_info(i):
  await asyncio.sleep(2)
  print(f'task {i} is running in this thread : {threading.current_thread().name}')

# define a main func, it will be used to create tasks, from coroutines and run them, and see the thread info
async def main():
    # create 10 tasks
  tasks = []
  for i in range(10):
    coro = print_thread_info(i)
    task = asyncio.create_task(coro)
    tasks.append(task)
  await asyncio.gather(*tasks)
asyncio.run(main())


# lab_task- 2.1.2
# Predict the output of the following code

async def task(name, delay):
  print(f"{name} starting ")
  await asyncio.sleep(delay)
  print(f"{name} Done")

async def main():
    t1 = task("A",3)
    t2 = task("B",1)
    t3 = task("C",2)
    tasks = [t1,t2,t3]
    print("Pridiction: Before running above tasks: A starting \nB starting \nC starting \nB Done \nC Done \nA Done ")
    await asyncio.gather(*tasks)

asyncio.run(main())

# lab_task- 2.1.3

async def blocking_task(name):
    print(f"{name}: Starting")
    # This blocks the ENTIRE thread. The Loop cannot switch to other tasks.
    time.sleep(1) 
    print(f"{name}: Done")

async def main():
    start = time.time()
    # We schedule them all "at once"
    t1 = asyncio.create_task(blocking_task("A"))
    t2 = asyncio.create_task(blocking_task("B"))
    t3 = asyncio.create_task(blocking_task("C"))
    
    await asyncio.gather(t1, t2, t3)
    
    print(f"Total Time: {time.time() - start:.2f} seconds")
    # Prediction: Total Time: 3.00 seconds
    # Actual: Total Time: 3.00 seconds
asyncio.run(main())

# lab_task- 2.1.4
# Run 100 tasks that each await 1 second
# Measure total execution time
# Is it 100 seconds? Or ~1 second?
# Explain why

async def wait_one_second():
        await asyncio.sleep(1)

async def main():
    start_time = time.time()
    tasks = [asyncio.create_task(wait_one_second()) for _ in range(100)]
    
    await asyncio.gather(*tasks)
    end_time = time.time()
    print(f"Total execution time: {end_time - start_time} seconds")

asyncio.run(main())