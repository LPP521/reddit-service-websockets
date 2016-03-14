import posixpath
import random

import gevent
import gevent.queue


def _walk_namespace_hierarchy(namespace):
    assert namespace.startswith("/")

    yield namespace
    while namespace != "/":
        namespace = posixpath.dirname(namespace)
        yield namespace


class MessageDispatcher(object):
    def __init__(self, metrics):
        self.consumers = {}
        self.metrics = metrics

    def on_message_received(self, namespace, message):
        consumers = self.consumers.get(namespace, [])

        with self.metrics.timer("dispatch"):
            for consumer in consumers:
                consumer.put(message)

    def listen(self, namespace, max_timeout):
        queue = gevent.queue.Queue()

        namespace = namespace.rstrip("/")
        for ns in _walk_namespace_hierarchy(namespace):
            self.consumers.setdefault(ns, []).append(queue)

        try:
            while True:
                # jitter the timeout a bit to ensure we don't herd
                timeout = max_timeout - random.uniform(0, max_timeout / 2)

                try:
                    yield queue.get(block=True, timeout=timeout)
                except gevent.queue.Empty:
                    yield None

                # ensure we're not starving others by spinning
                gevent.sleep()
        finally:
            for ns in _walk_namespace_hierarchy(namespace):
                self.consumers[ns].remove(queue)
                if not self.consumers[ns]:
                    del self.consumers[ns]