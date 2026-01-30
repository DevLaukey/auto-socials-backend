import logging

from app.workers.scheduler import SchedulerWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

if __name__ == "__main__":
    logging.getLogger("scheduler").info("Starting scheduler process")
    worker = SchedulerWorker(interval_seconds=30)
    worker.start()
