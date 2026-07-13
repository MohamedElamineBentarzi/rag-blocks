"""Storage subsystem: durable byte storage (the pipeline's source of truth).

Importing this package registers the built-in blob stores (module import is the
registration side effect the registry relies on). The vector store and lexical
index kinds will join this package in the v0.3 storage milestone.
"""

from .base import BlobStore
from .local import LocalBlobStore
from .minio_store import MinioBlobStore

__all__ = [
    "BlobStore",
    "LocalBlobStore",
    "MinioBlobStore",
]
