from dotenv import load_dotenv
import os

load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 768))
MIN_POOL_SIZE = int(os.getenv("MIN_POOL_SIZE", 2))
MAX_POOL_SIZE = int(os.getenv("MAX_POOL_SIZE", 10))
