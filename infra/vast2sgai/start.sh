#!/bin/bash
# The command the Lambda Web Adapter wrapper runs (AWS_LAMBDA_EXEC_WRAPPER):
# vast-2-sgai's own server, which the adapter forwards each request to.
exec node "$LAMBDA_TASK_ROOT/src/server.js"
