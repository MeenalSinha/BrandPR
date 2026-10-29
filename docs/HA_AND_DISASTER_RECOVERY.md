# BrandPR — Database High Availability, Backups & Disaster Recovery Runbook

**Environment:** Google Cloud Platform (GCP)  
**Region:** `asia-south1` (Mumbai)  
**Project ID:** `brandpr-512618`  
**Database Service:** Google Cloud SQL for PostgreSQL 16  
**Document Storage:** Google Cloud Storage (`brandpr-documents-512618`)

---

## 1. Executive Architecture Overview

To support enterprise-grade reliability without uncontrolled infrastructure spend, BrandPR establishes a tiered availability and recovery framework:

| Dimension | Current Demonstration Baseline | Hardened Production Configuration |
| :--- | :--- | :--- |
| **Availability Type** | `ZONAL` (`asia-south1-c`) | `REGIONAL` (Primary: `asia-south1-a`, Standby: `asia-south1-b`) |
| **Failover Mechanism** | Manual redeploy / zonal restart | Automatic synchronous standby failover (< 60s DNS switch) |
| **Automated Backups** | Daily at 02:00 UTC | Daily at 02:00 UTC, 30-day retention |
| **Point-In-Time Recovery** | Disabled | Enabled (continuous WAL archiving, 7-day log retention) |
| **Deletion Protection** | Disabled | Enabled (`deletion_protection = true`) |
| **Recovery Point Objective (RPO)** | 24 Hours | **< 5 Minutes** (via Write-Ahead Log transaction replay) |
| **Recovery Time Objective (RTO)** | 2–4 Hours | **< 15 Minutes** (failover) / **< 30 Minutes** (cross-region restore) |
| **Document Storage Resilience** | Standard GCS bucket | Object Versioning enabled, Nearline lifecycle after 90 days |

---

## 2. Recovery Objectives (RPO & RTO)

### 2.1 Recovery Point Objective (RPO): < 5 Minutes
- **Mechanism:** Continuous PostgreSQL Write-Ahead Log (WAL) streaming and archiving via Cloud SQL Point-In-Time Recovery (`point_in_time_recovery_enabled = true`).
- **Data Loss Boundary:** In the event of catastrophic primary node failure, transaction logs up to the last flushed write are preserved in redundant cloud storage, guaranteeing an RPO of under 5 minutes.

### 2.2 Recovery Time Objective (RTO): < 15 Minutes (Failover) / < 30 Minutes (Restore)
- **Automatic Zonal Failover (< 60s):** In a `REGIONAL` setup, Cloud SQL automatically detects primary zone unavailability, heartbeats fail, and the standby node in `asia-south1-b` assumes primary duties. Cloud Run backend instances automatically reconnect using the Cloud SQL Connector with exponential backoff.
- **Cross-Region / Out-of-Band Restore (< 30m):** Restoring a full database backup or PITR clone into a new instance in a secondary GCP region (e.g., `asia-south2`) requires approximately 18–25 minutes for a 50GB SSD volume.

---

## 3. Cost & Safety Analysis (Zonal vs. Regional HA)

Enabling Cloud SQL High Availability provisions a **synchronous standby replica** in a secondary availability zone that matches the CPU, RAM, and SSD storage of the primary instance.

```
Monthly Cost Breakdown (asia-south1):
---------------------------------------------------------------------------------
Configuration                   Zonal (Current)        Regional HA (Production)
---------------------------------------------------------------------------------
Instance (db-custom-2-7680)     ~$52.00 / month        ~$104.00 / month (2x compute)
SSD Storage (50 GB)             ~$8.50 / month         ~$17.00 / month (2x mirrored)
Automated Backups (30 days)     ~$4.00 / month         ~$8.00 / month
Point-In-Time Recovery WAL Logs Included               ~$6.00 / month (log storage)
---------------------------------------------------------------------------------
TOTAL ESTIMATED COST            ~$64.50 / month        ~$135.00 / month
```

> [!IMPORTANT]
> **Production Safety Rule:** In compliance with project guidelines, billable production infrastructure changes (e.g. toggling `REGIONAL` on the live Cloud SQL instance `brandpr-db`) are **staged and validated in configuration** (`infrastructure/cloudsql_ha.tf` and `infrastructure/gcloud_ha_upgrade.sh`) and require explicit client sign-off before cloud activation.

---

## 4. Disaster Recovery & Restoration Procedure

### 4.1 Safe Restoration Drill Script
BrandPR includes an automated, isolated restoration verification drill: [`scripts/db_restore_drill.py`](file:///C:/Users/Meenal%20Sinha/Downloads/BrandPR_Phase4/brandpr/scripts/db_restore_drill.py).

**Safety Guard:** The drill strictly refuses to run against production database connection strings. It requires a database name containing `test`, `recovery`, `drill`, or `staging`.

To execute a restore drill against a staging or test database:
```bash
python scripts/db_restore_drill.py "postgresql+psycopg://brandpr:secret@localhost:5433/brandpr_recovery"
```

The drill validates:
1. Database connectivity and PostgreSQL version compatibility.
2. Presence of all 19 core governance tables (brands, facts, revisions, content submissions, reviews, findings, impacts, campaigns, release decisions).
3. Record count audit across modules.
4. Complete foreign-key referential integrity check (0 orphaned records permitted).
5. Elapsed recovery duration measurement.

---

## 5. Cloud Storage Document Resilience

Uploaded PDF, TXT, and CSV ground truth files in `gs://brandpr-documents-512618` are safeguarded by the lifecycle policy in [`infrastructure/gcs_resilience.json`](file:///C:/Users/Meenal%20Sinha/Downloads/BrandPR_Phase4/brandpr/infrastructure/gcs_resilience.json):
- **Object Versioning:** Overwriting or updating a source document retains previous versions immutably.
- **Accidental Deletion Protection:** Non-current object versions are retained for 365 days before automatic cleanup.
- **Cost Optimization:** Documents older than 90 days transition to `NEARLINE` storage class automatically.

To apply the GCS resilience policy:
```bash
gcloud storage buckets update gs://brandpr-documents-512618 \
  --lifecycle-file=infrastructure/gcs_resilience.json \
  --versioning
```

