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
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  default     = "asia-south1" # Mumbai
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Cloud Storage Landing Bucket
resource "google_storage_bucket" "invoice_landing" {
  name                        = "${var.project_id}-invoice-landing"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning {
    enabled = false
  }
}

# 2. Cloud Firestore Native Database
resource "google_firestore_database" "database" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

# 3. Secret Manager
resource "google_secret_manager_secret" "finance_secrets" {
  secret_id = "finance-agent-secrets"
  replication {
    auto {}
  }
}

# 4. Pub/Sub Ingestion Topics
resource "google_pubsub_topic" "invoice_events" {
  name = "invoice-raw-topic"
}

resource "google_pubsub_topic" "invoice_dlq" {
  name = "invoice-dlq-topic"
}

# 5. GCS System Publisher IAM Binding
data "google_storage_project_service_account" "gcs_account" {}

resource "google_pubsub_topic_iam_member" "gcs_publisher" {
  topic  = google_pubsub_topic.invoice_events.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
}

resource "google_storage_notification" "gcs_notification" {
  bucket         = google_storage_bucket.invoice_landing.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.invoice_events.id
  event_types    = ["OBJECT_FINALIZE"]
  depends_on     = [google_pubsub_topic_iam_member.gcs_publisher]
}

# 6. Service Account with Least-Privilege IAM
resource "google_service_account" "agent_sa" {
  account_id   = "finance-agent-sa"
  display_name = "Autonomous Finance Agent Identity"
}

resource "google_project_iam_member" "vertex_access" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_project_iam_member" "firestore_access" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_project_iam_member" "storage_read" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "secret_access" {
  secret_id = google_secret_manager_secret.finance_secrets.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_sa.email}"
}
