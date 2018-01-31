import django
import redis

from rq.job import Job
from rq.queue import Queue

from django.conf import settings


class DjJob(Job):
    def _unpickle_data(self):
        django.setup()
        super(DjJob, self)._unpickle_data()


class DjQueue(Queue):
    job_class = DjJob

    def __init__(self, *args, **kwargs):
        rconn = redis.Redis(
            settings.REDIS['host'],
            settings.REDIS['port'],
            settings.REDIS['password']
        )
        kwargs["connection"] = rconn
        super(DjQueue, self).__init__(*args, **kwargs)

    def enqueue(self, *args, **kwargs):
        if not kwargs.get("ttl"):
            kwargs["ttl"] = 30
        if not kwargs.get("result_ttl"):
            kwargs["result_ttl"] = 30
        return super(DjQueue, self).enqueue(*args, **kwargs)
