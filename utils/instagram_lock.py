import time
import redis
import logging
import uuid

logger = logging.getLogger(__name__)

# Use a separate Redis DB from Celery if possible
redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=2,
    decode_responses=True,
)


class InstagramAccountLock:
    """
    Distributed lock to prevent concurrent Instagram logins
    for the same account (instagrapi safety).
    """

    def __init__(self, account_id: int, ttl_seconds: int = 600):
        self.account_id = account_id
        self.key = f"instagram:lock:{account_id}"
        self.ttl_seconds = ttl_seconds
        self.lock_value = str(uuid.uuid4())

    def acquire(self, wait_seconds: int = 30) -> bool:
        """
        Try to acquire the lock, waiting up to wait_seconds.
        """
        start = time.time()

        while time.time() - start < wait_seconds:
            try:
                acquired = redis_client.set(
                    self.key,
                    self.lock_value,
                    nx=True,
                    ex=self.ttl_seconds,
                )

                if acquired:
                    logger.info(
                        f"Instagram lock acquired for account {self.account_id}"
                    )
                    return True

            except redis.RedisError as exc:
                logger.error(
                    f"Redis error while acquiring Instagram lock: {exc}"
                )
                # Fail open to avoid total posting blockage
                return True

            time.sleep(1)

        logger.warning(
            f"Failed to acquire Instagram lock for account {self.account_id}"
        )
        return False

    def release(self):
        """
        Release the lock safely (only if owned by this worker).
        """
        try:
            current_value = redis_client.get(self.key)

            if current_value == self.lock_value:
                redis_client.delete(self.key)
                logger.info(
                    f"Instagram lock released for account {self.account_id}"
                )
            else:
                logger.warning(
                    f"Lock ownership mismatch for account {self.account_id}, not releasing"
                )

        except redis.RedisError as exc:
            logger.error(
                f"Redis error while releasing Instagram lock: {exc}"
            )
