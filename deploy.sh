#!/bin/bash
# Frontend-only deploy: pulls fresh data from live site before deploying.
# Usage: ./deploy.sh
# For pipeline changes: gh workflow run nursing-pipeline.yml --repo stableotto/nurseboard

set -e

echo "Pulling fresh data from live site..."
mkdir -p frontend/data

curl -sL "https://scrubshifts.com/data/jobs.json" -o frontend/data/jobs.json.tmp

# Only proceed if we got real data (not an error page)
SIZE=$(wc -c < frontend/data/jobs.json.tmp | tr -d ' ')
if [ "$SIZE" -lt 1000 ]; then
  echo "Error: jobs.json too small ($SIZE bytes), live site may be down. Aborting."
  rm frontend/data/jobs.json.tmp
  exit 1
fi

mv frontend/data/jobs.json.tmp frontend/data/jobs.json
curl -sL "https://scrubshifts.com/data/meta.json" -o frontend/data/meta.json
curl -sL "https://scrubshifts.com/data/cities.json" -o frontend/data/cities.json 2>/dev/null || true
curl -sL "https://scrubshifts.com/data/zips.json" -o frontend/data/zips.json 2>/dev/null || true

JOB_COUNT=$(python3 -c "import json; print(len(json.load(open('frontend/data/jobs.json'))))")
echo "Data ready: $JOB_COUNT jobs"

echo "Deploying to Cloudflare Pages..."
CLOUDFLARE_API_TOKEN="cfut_HTCrXaagdJ1K6BVBds2T5UZTU9QT6RLpZJdKHgGQd277420a" \
CLOUDFLARE_ACCOUNT_ID="45d0e2cb0865cb83661dab3a0554dd74" \
wrangler pages deploy frontend --project-name=scrubshifts --commit-dirty=true

echo "Done! $JOB_COUNT jobs deployed."
