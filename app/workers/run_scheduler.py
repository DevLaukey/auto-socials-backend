import logging
import threading
import time

from app.workers.scheduler import SchedulerWorker
from app.workers.analytics_worker import AnalyticsWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

if __name__ == "__main__":
    logging.getLogger("scheduler").info("Starting scheduler process")

    # Create workers
    scheduler_worker = SchedulerWorker(interval_seconds=30)
    analytics_worker = AnalyticsWorker(interval_seconds=600)

    # Start scheduler in thread
    scheduler_thread = threading.Thread(
        target=scheduler_worker.start,
        daemon=True,
    )

    # Start analytics worker in thread
    analytics_thread = threading.Thread(
        target=analytics_worker.start,
        daemon=True,
    )

    scheduler_thread.start()
    analytics_thread.start()

    # Keep main thread alive
    while True:
        time.sleep(1)
