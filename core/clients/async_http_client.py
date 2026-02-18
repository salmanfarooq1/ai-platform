import asyncio, aiohttp, logging
from typing import Optional

class AsyncHttpClient:
    # define __init__ method with necessary attributes ( created once, act like config, do not need to be async, values are decided based on industry best practices)
    # keep session and semaphore = None ( they need to be defined in async, we define them later in context management protocoal, as they are directly related tot he connection we create as session (handshake))
    def __init__(self, max_concurrent : int = 10, max_retries : int = 3, timeout : int = 10) -> None:
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.timeout = timeout
        self.session : Optional[aiohttp.ClientSession] = None
        self.semaphore : Optional[asyncio.Semaphore] = None

    # first part of context manager protocoal ( having this method allows the instance of this class to do *async with instance() as client:*)
    # here we create the connection resources, which is the session and semaphore. 
    # we return self as it is python way, and also, it makes sense as we pass self, get the resources created for self, and return self, it is like entering empty handed and coming out with a session and semaphore, using which we can make requests ( we will do that in fetch)) 
    async def __aenter__(self) -> "AsyncHttpClient":
        self.session = aiohttp.ClientSession()
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        return self
    

    # second part of context manager protocoal, it closes what __aenter__ created, no matter whatever exception occurs, if we entered with __aenter__, we would always come out with __aexit__. 
    # exc_type, exc_val, exc_tb, we only pass these as it is required in python
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.session.close()

    
    # here we create core function, that actually makes requests.
    # we pass a url, and self, and inside this, we  make a get request, and return response in case of success
    # we also handle retries using a for loop, and use exponential backoff using asyncio.sleep()
    # in case of failure despite max retries we do not wait and return the error
    # note that it only makes one request
    async def fetch(self, url: str) -> dict:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with self.semaphore:
                    async with self.session.get(url, timeout = self.timeout) as response:
                        if response.status == 200:
                            logging.info(f"fetched : -> {url}")
                            return await response.json()
                        else:
                            last_error = f'HTTP error : {response.status}'
            except Exception as e:
                last_error = str(e)
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return {'error' : last_error , 'url': url}

    # this is just the batch version, here we provide a list of urls and self.fetch() them one by one, and gather() them in the end, and return a list of responses for each url
    async def fetch_batch(self, urls : list[str]) -> list[dict]:
        tasks = []
        for url in urls:
            tasks.append(self.fetch(url))
        logging.info(f"Fetching {len(urls)} URLs with max_concurrent={self.max_concurrent}")
        return await asyncio.gather(*tasks, return_exceptions = True)
