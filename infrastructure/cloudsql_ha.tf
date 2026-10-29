# Terraform Configuration for Google Cloud SQL PostgreSQL 16 Regional High Availability (HA)
# Project: brandpr-512618 | Region: asia-south1 (Mumbai)

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  type        = string
  default     = "brandpr-512618"
  description = "Google Cloud Project ID"
}

variable "region" {
  type        = string
  default     = "asia-south1"
  description = "Primary Cloud SQL region"
}

variable "instance_name" {
  type        = string
  default     = "brandpr-db-ha"
  description = "Name of the Cloud SQL instance"
}

variable "database_version" {
  type        = string
  default     = "POSTGRES_16"
  description = "Target PostgreSQL database version"
}

variable "tier" {
  type        = string
  default     = "db-custom-2-7680" # 2 vCPU, 7.5 GB RAM (Production recommended)
  description = "Machine tier for the primary and standby nodes"
}

resource "google_sql_database_instance" "brandpr_ha" {
  name             = var.instance_name
  project          = var.project_id
  region           = var.region
  database_version = var.database_version

  deletion_protection = true

  settings {
    tier              = var.tier
    edition           = "ENTERPRISE"
    availability_type = "REGIONAL" # Enables synchronous standby replication across two zones (e.g., asia-south1-a and asia-south1-b)
    disk_type         = "PD_SSD"
    disk_size         = 50
    disk_autoresize   = true
    disk_autoresize_limit = 500

    location_preference {
      zone           = "asia-south1-a"
      secondary_zone = "asia-south1-b"
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "02:00" # 02:00 UTC (07:30 IST) daily automated backup window
      point_in_time_recovery_enabled = true    # Enables continuous Write-Ahead Log (WAL) archiving for 5-minute RPO
      backup_retention_settings {
        retained_backups = 30 # Retain 30 daily backups
        retention_unit   = "COUNT"
      }
      transaction_log_retention_days = 7
    }

    ip_configuration {
      ipv4_enabled    = true
      ssl_mode        = "ENCRYPTED_ONLY" # Enforce TLS/SSL for all incoming connections
      require_ssl     = true
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }
    database_flags {
      name  = "log_disconnections"
      value = "on"
    }
    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 3 # 03:00 UTC
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = false
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_sql_database" "brandpr_production" {
  name      = "brandpr"
  project   = var.project_id
  instance  = google_sql_database_instance.brandpr_ha.name
  charset   = "UTF8"
  collation = "en_US.UTF8"
}

# Output connection string template
output "connection_name" {
  value       = google_sql_database_instance.brandpr_ha.connection_name
  description = "Cloud SQL Connection Name for Cloud Run service integration"
}
