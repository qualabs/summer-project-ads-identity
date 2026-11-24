"""
lambda_handler.py

The ad server as an AWS Lambda behind a Function URL: the public URL that
MediaTailor (SSAI) and vast-2-sgai (SGAI) call. Same answers as server.py,
which is the same code on localhost.

  handler = lambda_handler.handler

It has no local files, so both settings come from the environment (infra/
sets them):

  BRIDGE_OUTPUT   where the bridge output is, normally s3://bucket/bridge
  AD_MEDIA_BASE   where the packaged ad is served from
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402
import source  # noqa: E402

_read_hand_ids = None


def respond(event, read_hand_ids, media_base):
    """event is a Function URL request (payload format 2.0)."""
    def reply(status, body, content_type):
        return {"statusCode": status, "headers": {"Content-Type": content_type, **server.HEADERS}, "body": body}

    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method != "GET":
        return reply(405, "method not allowed\n", server.TEXT)
    return reply(*server.answer(read_hand_ids, media_base, event.get("rawPath", "/"),
                                event.get("rawQueryString", "")))


def handler(event, context):
    global _read_hand_ids
    if _read_hand_ids is None:  # once per execution environment, not per request
        _read_hand_ids = source.reader(os.environ["BRIDGE_OUTPUT"])
    return respond(event, _read_hand_ids, os.environ["AD_MEDIA_BASE"])
