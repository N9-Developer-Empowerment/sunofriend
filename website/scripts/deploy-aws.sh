#!/usr/bin/env bash
set -euo pipefail

SITE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_NAME="${STACK_NAME:-sunofriend-site}"
SITE_AWS_REGION="${AWS_REGION:-eu-west-2}"
DOMAIN_NAME="${DOMAIN_NAME:-}"
ALTERNATE_DOMAIN_NAME="${ALTERNATE_DOMAIN_NAME:-}"
CERTIFICATE_ARN="${CERTIFICATE_ARN:-}"

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI v2 is required." >&2
  exit 1
fi

aws sts get-caller-identity >/dev/null

CFN_ARGS=(
  --template-file "$SITE_ROOT/infra/site.yaml"
  --stack-name "$STACK_NAME"
  --region "$SITE_AWS_REGION"
  --no-fail-on-empty-changeset
)

if [[ -n "$DOMAIN_NAME" ]]; then
  if [[ -z "$CERTIFICATE_ARN" ]]; then
    echo "CERTIFICATE_ARN is required when DOMAIN_NAME is set." >&2
    exit 1
  fi
  CFN_ARGS+=(
    --parameter-overrides
    "DomainName=$DOMAIN_NAME"
    "AlternateDomainName=$ALTERNATE_DOMAIN_NAME"
    "CertificateArn=$CERTIFICATE_ARN"
  )
fi

aws cloudformation deploy "${CFN_ARGS[@]}"

SITE_BUCKET="$(
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$SITE_AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue" \
    --output text
)"
DISTRIBUTION_ID="$(
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$SITE_AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
    --output text
)"
SITE_URL="$(
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$SITE_AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='SiteUrl'].OutputValue" \
    --output text
)"

cd "$SITE_ROOT"
NEXT_PUBLIC_SITE_URL="$SITE_URL" npm run build:aws

aws s3 sync "$SITE_ROOT/out/" "s3://$SITE_BUCKET/" \
  --region "$SITE_AWS_REGION" \
  --delete \
  --exclude "*.html" \
  --cache-control "public,max-age=31536000,immutable"

aws s3 cp "$SITE_ROOT/out/" "s3://$SITE_BUCKET/" \
  --region "$SITE_AWS_REGION" \
  --recursive \
  --exclude "*" \
  --include "*.html" \
  --cache-control "no-cache,no-store,must-revalidate"

aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  >/dev/null

echo "$SITE_URL"
