#!/usr/bin/env bash
# ==============================================================================
# BrandPR Cloud SQL Regional HA & Resilience Upgrade Script
# Target Instance: brandpr-db | Project: brandpr-512618 | Region: asia-south1
#
# NOTICE: This script applies configuration upgrades for production resilience:
#   1. Regional High Availability (synchronous standby failover)
#   2. Point-In-Time Recovery (PITR) with transaction log archiving
#   3. Automated daily backups with 30-day retention
#   4. Deletion protection
#
# Cost Impact: Enabling REGIONAL availability adds approximately 100% to the
# base instance compute/RAM cost because of the synchronous standby node.
# ==============================================================================

set -euo pipefail

PROJECT_ID="brandpr-512618"
INSTANCE_NAME="brandpr-db"
REGION="asia-south1"

echo "=== BRANDPR CLOUD SQL RESILIENCE UPGRADE PROCEDURE ==="
echo "Target Project:  ${PROJECT_ID}"
echo "Target Instance: ${INSTANCE_NAME} (${REGION})"

# 1. Enable automated backups and point-in-time recovery (WAL archiving)
echo "Step 1: Enabling automated backups and Point-In-Time Recovery (PITR)..."
gcloud sql instances patch "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --backup-start-time="02:00" \
  --enable-bin-log \
  --retained-backups-count=30 \
  --retained-transaction-log-days=7

# 2. Enable deletion protection
echo "Step 2: Enabling deletion protection..."
gcloud sql instances patch "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --deletion-protection

# 3. Upgrade to Regional High Availability (Execute only when billable HA is approved)
echo "Step 3: Upgrading availability type to REGIONAL..."
gcloud sql instances patch "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --availability-type=REGIONAL

# 4. Trigger an on-demand baseline backup
echo "Step 4: Creating baseline on-demand backup..."
gcloud sql backups create \
  --instance="${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --description="Baseline backup prior to regional HA operation"

echo "=== UPGRADE PROCEDURE COMPLETED SUCCESSFULLY ==="
