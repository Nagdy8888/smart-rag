"""Reproduce scan_object_bytes against the demo CSV from the worker."""

from __future__ import annotations

import os
import time

from smart_rag_core.gateways.clamav import ClamAvClient
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.scan import ObjectScanInput, scan_object_bytes

BUCKET = "documents-quarantine"
PATH = (
    "4b17eaa6-2cc4-4b40-98da-61af50b8e676/"
    "d17736d6-3511-437e-acbc-e213b575891c/"
    "movie.metadata.demo.csv"
)


def main() -> None:
    """Download and scan the reserved object."""

    url = os.environ.get("SUPABASE_URL") or "http://host.docker.internal:54321"
    secret = os.environ.get("SUPABASE_STORAGE_ADMIN_SECRET") or ""
    print("url_ok", url.endswith("54321"), "secret_len", len(secret), flush=True)
    storage = StorageGateway(supabase_url=url, admin_secret=secret)
    clamav = ClamAvClient(host="clamav", port=3310, timeout_seconds=30)
    t0 = time.monotonic()
    data = storage.download_object(bucket=BUCKET, object_path=PATH)
    print("download", len(data), round(time.monotonic() - t0, 3), flush=True)
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    t1 = time.monotonic()
    result = scan_object_bytes(
        storage,
        clamav,
        ObjectScanInput(
            bucket=BUCKET,
            path=PATH,
            expected_hash=digest,
            expected_bytes=len(data),
        ),
    )
    print(
        "scan",
        result.result,
        round(time.monotonic() - t1, 3),
        result.details.get("detail"),
        flush=True,
    )


if __name__ == "__main__":
    main()
