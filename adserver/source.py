"""
source.py

Where the ad server finds the bridge output. One location string, three forms:

  out/bridge                     a local folder (the default)
  https://cdn.example/bridge     a base URL, read over HTTP(S)
  s3://bucket/prefix             an S3 prefix, read with boto3

Under it the layout is always the same: hand_ids.json for the default ad and
<name>/hand_ids.json for a named one.

reader(location) returns a function ad -> parsed hand_ids.json, or None when
there is no such file: the bridge did not trust that ad, or never ran. Any
other failure (network down, bad JSON) raises, and the server answers "no ad"
for that too: an ad whose IDs we can't read is never served.
"""

import json
import urllib.error
import urllib.request
from pathlib import Path

FILE = "hand_ids.json"
TIMEOUT = 5  # seconds, for the remote forms


def _key(ad):
    return FILE if ad is None else f"{ad}/{FILE}"


def _local(folder):
    def read(ad):
        try:
            return json.loads((folder / _key(ad)).read_text(encoding="utf-8"))
        except (FileNotFoundError, NotADirectoryError):
            return None
    return read


def _http(base):
    def read(ad):
        try:
            with urllib.request.urlopen(f"{base}/{_key(ad)}", timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # S3 and CloudFront answer 403, not 404, for a missing object when
            # the caller may not list the bucket.
            if e.code in (403, 404):
                return None
            raise
    return read


def _s3(bucket, prefix, client=None):
    if client is None:
        import boto3  # only needed for s3://; present in the Lambda runtime
        client = boto3.client("s3")

    def read(ad):
        key = f"{prefix}/{_key(ad)}" if prefix else _key(ad)
        try:
            body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        except client.exceptions.NoSuchKey:
            return None
        return json.loads(body.decode("utf-8"))
    return read


def reader(location, s3_client=None):
    location = str(location)
    if location.startswith(("http://", "https://")):
        return _http(location.rstrip("/"))
    if location.startswith("s3://"):
        bucket, _, prefix = location[len("s3://"):].partition("/")
        if not bucket:
            raise ValueError(f"no bucket in {location!r}")
        return _s3(bucket, prefix.strip("/"), s3_client)
    return _local(Path(location))
