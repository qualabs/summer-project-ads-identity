# The ad server (adserver/) as a Lambda behind a public Function URL: the URL
# MediaTailor and vast-2-sgai call for the VAST. It reads the bridge output
# from bridge/ in the bucket and points the MediaFiles at ad/ on CloudFront.

locals {
  adserver_files = ["lambda_handler.py", "server.py", "source.py", "vast.py"]
}

data "archive_file" "adserver" {
  type        = "zip"
  output_path = "${path.module}/.build/adserver.zip"

  dynamic "source" {
    for_each = local.adserver_files
    content {
      filename = source.value
      content  = file("${path.module}/../adserver/${source.value}")
    }
  }
}

data "aws_iam_policy_document" "adserver_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# No s3:ListBucket on purpose: S3 then answers AccessDenied for a missing
# hand_ids.json, which adserver/source.py reads as "no such ad".
data "aws_iam_policy_document" "adserver" {
  statement {
    sid       = "ReadTheBridgeOutput"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.media.arn}/bridge/*"]
  }

  statement {
    sid       = "WriteItsLog"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.adserver.arn}:*"]
  }
}

resource "aws_iam_role" "adserver" {
  name               = "${var.name}-adserver"
  assume_role_policy = data.aws_iam_policy_document.adserver_assume.json
}

resource "aws_iam_role_policy" "adserver" {
  name   = "adserver"
  role   = aws_iam_role.adserver.id
  policy = data.aws_iam_policy_document.adserver.json
}

resource "aws_cloudwatch_log_group" "adserver" {
  name              = "/aws/lambda/${var.name}-adserver"
  retention_in_days = 14
}

resource "aws_lambda_function" "adserver" {
  function_name    = "${var.name}-adserver"
  role             = aws_iam_role.adserver.arn
  runtime          = "python3.13" # includes boto3, which source.py needs for s3://
  handler          = "lambda_handler.handler"
  filename         = data.archive_file.adserver.output_path
  source_code_hash = data.archive_file.adserver.output_base64sha256
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      BRIDGE_OUTPUT = "s3://${aws_s3_bucket.media.bucket}/bridge"
      AD_MEDIA_BASE = "${local.media_url}/ad"
    }
  }

  depends_on = [aws_cloudwatch_log_group.adserver, aws_iam_role_policy.adserver]
}

# Public, no auth: MediaTailor and vast-2-sgai call it as any ad server. The
# function sets its own CORS header, so the URL has no cors block (two would
# duplicate the header).
resource "aws_lambda_function_url" "adserver" {
  function_name      = aws_lambda_function.adserver.function_name
  authorization_type = "NONE"
}

# A public Function URL needs both permissions.
resource "aws_lambda_permission" "adserver_url" {
  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.adserver.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "adserver_invoke" {
  statement_id             = "PublicInvokeViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.adserver.function_name
  principal                = "*"
  invoked_via_function_url = true
}

locals {
  vast_url = "${aws_lambda_function_url.adserver.function_url}vast"
}
