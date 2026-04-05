#!/bin/bash
# Frontend-only deploy: pulls fresh data from live site before deploying.
# Use this for CSS/JS/HTML changes. For pipeline changes, use:
#   gh workflow run nursing-pipeline.yml --repo stableotto/nurseboard

set -e

echo "Pulling fresh data from live site..."
mkdir -p frontend/data

# Download current live jobs.json and meta.json
curl -sL "https://scrubshifts.com/data/jobs.json" -o frontend/data/jobs.json
curl -sL "https://scrubshifts.com/data/meta.json" -o frontend/data/meta.json

# Download zips.json if not present locally
if [ ! -f frontend/data/zips.json ]; then
  curl -sL "https://scrubshifts.com/data/zips.json" -o frontend/data/zips.json
fi
curl -sL "https://scrubshifts.com/data/cities.json" -o frontend/data/cities.json

# Sync job detail JSON files
echo "Syncing job detail files..."
# Get the list of detail prefixes from jobs.json
python3 -c "
import json, os, requests

with open('frontend/data/jobs.json') as f:
    jobs = json.load(f)

prefixes = set(j['id'][:2] for j in jobs)
base = 'https://scrubshifts.com/data/jobs'

for prefix in prefixes:
    os.makedirs(f'frontend/data/jobs/{prefix}', exist_ok=True)

for j in jobs:
    jid = j['id']
    prefix = jid[:2]
    path = f'frontend/data/jobs/{prefix}/{jid}.json'
    if not os.path.exists(path):
        r = requests.get(f'{base}/{prefix}/{jid}.json', timeout=5)
        if r.status_code == 200:
            with open(path, 'w') as f:
                f.write(r.text)

print(f'Synced detail files for {len(jobs)} jobs')
"

JOB_COUNT=$(python3 -c "import json; print(len(json.load(open('frontend/data/jobs.json'))))")
echo "Data ready: $JOB_COUNT jobs"

echo "Deploying to Cloudflare Pages..."
CLOUDFLARE_API_TOKEN="cfut_HTCrXaagdJ1K6BVBds2T5UZTU9QT6RLpZJdKHgGQd277420a" \
CLOUDFLARE_ACCOUNT_ID="45d0e2cb0865cb83661dab3a0554dd74" \
wrangler pages deploy frontend --project-name=scrubshifts --commit-dirty=true

echo "Done!"
