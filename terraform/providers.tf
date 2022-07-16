terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.25.0"
    }
  }
}


provider "google" {
  project = var.project-id
}