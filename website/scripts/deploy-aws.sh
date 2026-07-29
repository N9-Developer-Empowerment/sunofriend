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

build_and_validate_static_site() {
  local site_url="$1"
  cd "$SITE_ROOT"
  NEXT_PUBLIC_SITE_URL="$site_url" npm run build:aws
  if [[ ! -s "$SITE_ROOT/out/404.html" ]]; then
    echo "Static build did not create out/404.html; refusing to update CloudFront." >&2
    exit 1
  fi
  if ! grep -q "This page is silent" "$SITE_ROOT/out/404.html"; then
    echo "Static 404 output did not contain the expected branded page." >&2
    exit 1
  fi
}

PREBUILD_SITE_URL="${NEXT_PUBLIC_SITE_URL:-}"
if [[ -z "$PREBUILD_SITE_URL" && -n "$DOMAIN_NAME" ]]; then
  PREBUILD_SITE_URL="https://$DOMAIN_NAME"
fi
PREBUILD_SITE_URL="${PREBUILD_SITE_URL:-https://sunofriend.com}"

# Build and verify the page used by CustomErrorResponses before changing that
# mapping. A broken export therefore cannot point CloudFront at a missing file.
build_and_validate_static_site "$PREBUILD_SITE_URL"

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

if [[ "$SITE_URL" != "$PREBUILD_SITE_URL" ]]; then
  # A first deployment without a custom domain learns its CloudFront URL only
  # after stack creation. Rebuild metadata for that final URL and revalidate.
  build_and_validate_static_site "$SITE_URL"
fi

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
