import urllib

import packaging.version

from ..util import get_dependency
from .redis import RedisStorage

MIN_REDIS_PY = packaging.version.parse("4.1.0")


class RedisClusterStorage(RedisStorage):
    """
    Rate limit storage with redis cluster as backend

    Depends on :pypi:`redis-cluster-py`
    """

    STORAGE_SCHEME = ["redis+cluster"]
    """The storage scheme for redis cluster"""

    DEFAULT_OPTIONS = {
        "max_connections": 1000,
    }
    "Default options passed to the :class:`~redis.cluster.RedisCluster`"

    DEPENDENCIES = ["redis"]

    def __init__(self, uri: str, **options):
        """
        :param uri: url of the form
         ``redis+cluster://[:password]@host:port,host:port``
        :param options: all remaining keyword arguments are passed
         directly to the constructor of :class:`redis.cluster.RedisCluster`
        :raise ConfigurationError: when the :pypi:`redis` library is not
         available or if the redis host cannot be pinged.
        """
        parsed = urllib.parse.urlparse(uri)
        cluster_hosts = []
        for loc in parsed.netloc.split(","):
            host, port = loc.split(":")
            cluster_hosts.append({"host": host, "port": int(port)})

        self.storage = self._get_storage(
            startup_nodes=cluster_hosts, **{**self.DEFAULT_OPTIONS, **options}
        )
        self.initialize_storage(uri)
        super(RedisStorage, self).__init__()

    def _get_storage(self, startup_nodes, **kwargs):
        if (
            packaging.version.parse(self.dependencies["redis"].__version__)
            < MIN_REDIS_PY
        ):
            return get_dependency("rediscluster").RedisCluster(
                startup_nodes=startup_nodes, **kwargs
            )
        else:
            nodes = [
                self.dependencies["redis"].cluster.ClusterNode(h["host"], h["port"])
                for h in startup_nodes
            ]
            return self.dependencies["redis"].cluster.RedisCluster(
                startup_nodes=nodes, **kwargs
            )

    def reset(self) -> int:
        """
        Redis Clusters are sharded and deleting across shards
        can't be done atomically. Because of this, this reset loops over all
        keys that are prefixed with 'LIMITER' and calls delete on them, one at
        a time.

        .. warning::
         This operation was not tested with extremely large data sets.
         On a large production based system, care should be taken with its
         usage as it could be slow on very large data sets"""

        keys = self.storage.keys("LIMITER*")
        return sum([self.storage.delete(k.decode("utf-8")) for k in keys])
