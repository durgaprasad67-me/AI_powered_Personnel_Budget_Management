import os
from dotenv import load_dotenv

# Loads backend/.env when running from the backend directory.
load_dotenv()

MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_CLUSTER = os.getenv("MONGO_CLUSTER")
DATABASE_NAME = os.getenv("DATABASE_NAME", "finsight_db")
