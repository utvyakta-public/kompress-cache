# Kompress Cache

Redis-based cache that routes write operations to a primary Redis instance and read operations to replicas, with automatic failover to the primary in case of replica failure.



## Configuration options - Environment variables
| Environment Variable | Description                                                    | Default Value                        | Comments                                                 | Since |
|----------------------|----------------------------------------------------------------|--------------------------------------|----------------------------------------------------------|-------|
| REDIS_HOST           | Hostname/ IP Address of the Primary Redis cache                        | `localhost`                          |        | 0.1.0 |
| REDIS_PORT           | Port of the Primary Redis cache                        | `6379`                          |        | 0.1.0 |
| REDIS_REPLICAS_HOST_PORT               | Comma separated redis replicas host port                                    |  | Example: replica1:6379,replica2:6379 If no replicas provided, the primary redis server will be used for both read and write operations. | 0.1.0 |
| REDIS_TIMEOUT              | Timeout for a redis command execution in seconds                                 | 5                            |                                                          | 0.1.0 |



## Usage

- Ensure that all configurations are setup and the given redis servers are running.
- `kompress_cache` logger need to be configured. for more verbose logs, set the logger level to DEBUG.
```
from kompress_cache import get_cache

cache = get_cache()

# uses primary redis
cache.hset("myhash", "key1", "value1")  # otuput: 1

# uses one of the given replicas to retrieve a data. When the replica fails, it gracefully switches to primary to retrieve the data
cache.hget("myhash", "key1")    # output: value1
```


## Authors and acknowledgment
1. sudhir.ravindramohan@utvyakta.com
2. poovarasan.v@utvyakta.com
