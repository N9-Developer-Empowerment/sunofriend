#!/usr/bin/env bash
set -euo pipefail

SITE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DOMAIN="${ROOT_DOMAIN:-sunofriend.com}"
ALTERNATE_DOMAIN="${ALTERNATE_DOMAIN:-www.sunofriend.com}"
DOMAIN_STACK_NAME="${DOMAIN_STACK_NAME:-sunofriend-domain}"
SITE_STACK_NAME="${STACK_NAME:-sunofriend-site}"
SITE_AWS_REGION="${AWS_REGION:-eu-west-2}"
CERTIFICATE_ARN="${CERTIFICATE_ARN:?Set CERTIFICATE_ARN to the validated us-east-1 ACM certificate.}"

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI v2 is required." >&2
  exit 1
fi

CERTIFICATE_STATUS="$(
  aws acm describe-certificate \
    --certificate-arn "$CERTIFICATE_ARN" \
    --region us-east-1 \
    --query "Certificate.Status" \
    --output text
)"

if [[ "$CERTIFICATE_STATUS" != "ISSUED" ]]; then
  echo "The ACM certificate is $CERTIFICATE_STATUS, not ISSUED." >&2
  exit 1
fi

read -r ROOT_VALIDATION_NAME ROOT_VALIDATION_VALUE <<<"$(
  aws acm describe-certificate \
    --certificate-arn "$CERTIFICATE_ARN" \
    --region us-east-1 \
    --query "Certificate.DomainValidationOptions[?DomainName=='$ROOT_DOMAIN'].ResourceRecord.[Name,Value] | [0]" \
    --output text
)"

read -r ALTERNATE_VALIDATION_NAME ALTERNATE_VALIDATION_VALUE <<<"$(
  aws acm describe-certificate \
    --certificate-arn "$CERTIFICATE_ARN" \
    --region us-east-1 \
    --query "Certificate.DomainValidationOptions[?DomainName=='$ALTERNATE_DOMAIN'].ResourceRecord.[Name,Value] | [0]" \
    --output text
)"

if [[ -z "$ROOT_VALIDATION_NAME" || -z "$ROOT_VALIDATION_VALUE" ||
      -z "$ALTERNATE_VALIDATION_NAME" || -z "$ALTERNATE_VALIDATION_VALUE" ]]; then
  echo "Could not read both ACM validation records." >&2
  exit 1
fi

STACK_NAME="$SITE_STACK_NAME" \
AWS_REGION="$SITE_AWS_REGION" \
DOMAIN_NAME="$ROOT_DOMAIN" \
ALTERNATE_DOMAIN_NAME="$ALTERNATE_DOMAIN" \
CERTIFICATE_ARN="$CERTIFICATE_ARN" \
  "$SITE_ROOT/scripts/deploy-aws.sh"

CLOUDFRONT_DOMAIN="$(
  aws cloudformation describe-stacks \
    --stack-name "$SITE_STACK_NAME" \
    --region "$SITE_AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='DistributionDomainName'].OutputValue" \
    --output text
)"

aws cloudformation deploy \
  --template-file "$SITE_ROOT/infra/domain-zone.yaml" \
  --stack-name "$DOMAIN_STACK_NAME" \
  --region "$SITE_AWS_REGION" \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "RootDomain=$ROOT_DOMAIN" \
    "AlternateDomain=$ALTERNATE_DOMAIN" \
    "CloudFrontDomainName=$CLOUDFRONT_DOMAIN" \
    "RootValidationRecordName=$ROOT_VALIDATION_NAME" \
    "RootValidationRecordValue=$ROOT_VALIDATION_VALUE" \
    "AlternateValidationRecordName=$ALTERNATE_VALIDATION_NAME" \
    "AlternateValidationRecordValue=$ALTERNATE_VALIDATION_VALUE"

aws cloudformation describe-stacks \
  --stack-name "$DOMAIN_STACK_NAME" \
  --region "$SITE_AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='NameServers'].OutputValue" \
  --output text
