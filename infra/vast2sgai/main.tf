# vast-2-sgai (montevideo-tech/vast-2-sgai) as a Lambda behind a public
# Function URL: the X-ASSET-LIST the SGAI interstitial points to. It turns the
# VAST of the ad server (infra/) into an HLS Interstitials asset list.
#
# The code is not changed. vast-2-sgai is an Express server (node
# src/server.js, port 3000); the AWS Lambda Web Adapter layer forwards each
# Function URL request to it. A second, tiny layer holds start.sh, the command
# the adapter's wrapper runs, so the function zip is the clone as it is.

locals {
  lwa_layer_arn = "arn:aws:lambda:${var.region}:753240598075:layer:LambdaAdapterLayerX86:${var.lwa_layer_version}"
  vast_host     = split("/", var.vast_url)[2]
}

# The clone, minus what the server does not need. .env is left out on purpose:
# its values are examples, the configuration is the environment below.
data "archive_file" "app" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.module}/.build/vast2sgai.zip"
  excludes = [
    ".env", "src/.env", ".env.example",
    ".git", ".git/**", ".github", ".github/**",
    "infra", "infra/**", "hls.js", "hls.js/**",
    "Dockerfile", "docker-compose.yml", "eslint.config.mjs",
  ]
}

# From a file, not an inline `source` block: only files get output_file_mode,
# and Lambda needs start.sh executable. .gitattributes keeps it LF on Windows.
data "archive_file" "start" {
  type             = "zip"
  output_path      = "${path.module}/.build/start-layer.zip"
  output_file_mode = "0755"
  source_file      = "${path.module}/start.sh"
}

resource "aws_lambda_layer_version" "start" {
  layer_name          = "${var.name}-vast2sgai-start"
  filename            = data.archive_file.start.output_path
  source_code_hash    = data.archive_file.start.output_base64sha256
  compatible_runtimes = [var.runtime]
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Only its log. It reads the VAST over HTTPS, like any client.
data "aws_iam_policy_document" "vast2sgai" {
  statement {
    sid       = "WriteItsLog"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.vast2sgai.arn}:*"]
  }
}

resource "aws_iam_role" "vast2sgai" {
  name               = "${var.name}-vast2sgai"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "vast2sgai" {
  name   = "vast2sgai"
  role   = aws_iam_role.vast2sgai.id
  policy = data.aws_iam_policy_document.vast2sgai.json
}

resource "aws_cloudwatch_log_group" "vast2sgai" {
  name              = "/aws/lambda/${var.name}-vast2sgai"
  retention_in_days = 14
}

resource "aws_lambda_function" "vast2sgai" {
  function_name    = "${var.name}-vast2sgai"
  role             = aws_iam_role.vast2sgai.arn
  runtime          = var.runtime
  handler          = "src/server.js" # not used: start.sh runs the server
  filename         = data.archive_file.app.output_path
  source_code_hash = data.archive_file.app.output_base64sha256
  layers           = [local.lwa_layer_arn, aws_lambda_layer_version.start.arn]
  timeout          = 30
  memory_size      = 512

  environment {
    variables = {
      # Lambda Web Adapter
      AWS_LAMBDA_EXEC_WRAPPER      = "/opt/start.sh"
      AWS_LWA_PORT                 = "3000"
      AWS_LWA_READINESS_CHECK_PATH = "/"

      # vast-2-sgai (see its .env.example)
      PORT             = "3000"
      NODE_ENV         = "production"
      PINO_LOG_LEVEL   = "info"
      VAST_WHITELIST   = local.vast_host # only our ad server's VAST
      ORIGIN_WHITELIST = var.origin_whitelist
      API_DISABLE_SIGN = "true" # /api/sign off: we pass vasturl, not a JWT
    }
  }

  depends_on = [aws_cloudwatch_log_group.vast2sgai, aws_iam_role_policy.vast2sgai]
}

# Public, no auth: the player calls it from the browser. vast-2-sgai sets its
# own CORS headers (cors()), so the URL has no cors block.
resource "aws_lambda_function_url" "vast2sgai" {
  function_name      = aws_lambda_function.vast2sgai.function_name
  authorization_type = "NONE"
}

# A public Function URL needs both permissions.
resource "aws_lambda_permission" "url" {
  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.vast2sgai.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "invoke" {
  statement_id             = "PublicInvokeViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.vast2sgai.function_name
  principal                = "*"
  invoked_via_function_url = true
}
