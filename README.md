# Kompress Cache

Redis-based cache that routes write operations to a primary Redis instance and read operations to replicas, with automatic failover to the primary in case of replica failure. This package is designed to work seamlessly with FastAPI, making it ideal for modern python web applications.

---

## 🔧 Features

- ✅ Async Redis support with graceful error handling
- ✅ Automatic failover from replica to primary
- ✅ Schema validation for cached values using Pydantic
- ✅ Custom cache miss loading via `Loadable` interface
- ✅ Support for primary and multiple replicas
- ✅ Configurable via environment variables

---


## ⚙️ Configuration options - Environment variables
| Environment Variable | Description                                                    | Default Value                        | Comments                                                 | Since |
|----------------------|----------------------------------------------------------------|--------------------------------------|----------------------------------------------------------|-------|
| REDIS_HOST           | Hostname/ IP Address of the Primary Redis cache                        | `localhost`                          |        | 0.1.0 |
| REDIS_PORT           | Port of the Primary Redis cache                        | `6379`                          |        | 0.1.0 |
| REDIS_REPLICAS_HOST_PORT               | Comma separated redis replicas host port                                    |  | Example: localhost:6380,localhost:6381 If no replicas provided, the primary redis server will be used for both read and write operations. | 0.1.0 |
| REDIS_TIMEOUT              | Timeout for a redis command execution in seconds                                 | 5                            |                                                          | 0.1.0 |
---



## 💡 Usage

- Ensure that all configurations are setup and the given redis servers are running.
- `kompress_cache` logger need to be configured. For more verbose logs, set the logger level to DEBUG.

### 🔹 Basic Usage (No Validation)
```
import json
from kompress_cache import get_cache

cache = get_cache()

user = {"id": "1", "name": "Alice"}

# Set data in Redis (uses the primary Redis instance)
await cache.hset("users", user["id"], json.dumps(user))  # Output: 1

user_id = "1"

# Retrieve data from one of the replicas; fails over to primary if needed
user_cache = await cache.hget("users", user_id)  # Output: '{"id": "1", "name": "Alice"}'

if user_cache is None:
    print("User cache not found. Fetching from DB...")
    user_data = get_user_data_from_db(user_id)
else:
    user_data = json.loads(user_cache)

print(user_data)

```

### 🚨 Exception Handling
Redis connection issues are automatically caught and converted to appropriate FastAPI HTTPException errors:

|   Redis Error           |   HTTP Status Code    |             Message      |
|-------------------------|-----------------------|--------------------------|
|   `ConnectionError`     |         503           |   Service Unavailable    |
|    `TimeoutError`       |         504           |   Gateway Timeout        |
| `Other Redis Exception` |         500           |   Internal Server Error  |

This means you can focus on your logic and let the cache gracefully degrade:
```
from fastapi import FastAPI, HTTPException
from kompress_cache import get_cache, Loadable
from myapp.models import UserModel
from myapp.db import get_user_data_from_db

app = FastAPI()
cache = get_cache()

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    try:
        user_loader = MyUserLoader(user_id)
        return await cache.hget_l("users", user_id, user_loader, UserModel)
    except HTTPException as e:
        if e.status_code in (503, 504):
            return await get_user_data_from_db(user_id)
        raise

```

### 🔸 Smart Caching with Pydantic + Loader
Let's take it further using the power of Pydantic and cache-miss loaders.
```
from pydantic import BaseModel
from kompress_cache import get_cache, Loadable

cache = get_cache()

# Define your Pydantic model
class UserModel(BaseModel):
    id: str
    name: str

# Create a loader for cache misses
class UserLoader(Loadable):
    def __init__(self, user_id: str):
        self.user_id = user_id

    async def load(self) -> str:
        user_data = await get_user_data_from_db_or_external_api(self.user_id)
        return UserModel(**user_data).model_dump_json()

user_id = "1"
user_loader = UserLoader(user_id)

# Retrieve the user data
user_data = await cache.hget_l("users", user_id, user_loader, UserModel)

# If data is:
# - not in cache → it is loaded via the loader and cached.
# - in cache → the data is validated against the given BaseModel and if data is:
#       - invalid → it is refreshed via the loader.
#       - valid → returned as a validated model instance.

print(user_data.id)   # "1"
print(user_data.name) # "Alice"

```

### 🔁 Evolving Schema with Automatic Refresh
Imagine you update your user schema to include an age field:
```
class UserModel(BaseModel):
    id: str
    name: str
    age: int
```

- If the cache still has the old schema (without age), validation will fail.

- The hget_l method will detect this, trigger the loader, and update the cache with the latest schema.

✅ No need to manually invalidate the cache — just update your model!


---

## 🧪 Built for Async
Your cache logic works natively with async functions. Whether using FastAPI background tasks or high-throughput endpoints, Redis calls are non-blocking, thanks to `redis.asyncio`.


---


## 🤝 Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you’d like to change.


---

## 📜 License

[MIT](/LICENSE)

---


## Authors and acknowledgment
1. sudhir.ravindramohan@utvyakta.com
2. poovarasan.v@utvyakta.com
