import logging
from app.celery_app import celery_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

if __name__ == "__main__":
    logging.getLogger("celery").info("Celery worker must be started via CLI")
