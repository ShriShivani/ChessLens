variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = <<-EOT
    EC2 instance type. Must be Free Plan eligible for your account; check with:
    aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true --query "InstanceTypes[].InstanceType"
    (accounts created on or after 2025-07-15 list t3.micro, t3.small, t4g.micro, t4g.small, c7i-flex.large, m7i-flex.large)
    The deploy script pulls x86_64 images, so keep an x86 type such as t3.micro.
  EOT
  type        = string
  default     = "t3.micro"
}

variable "github_repo" {
  description = "GitHub repository allowed to deploy, as OWNER/REPO."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repo))
    error_message = "github_repo must look like OWNER/REPO."
  }
}

variable "github_environment" {
  description = "GitHub Actions environment whose jobs may assume the deploy role (has the approval gate)."
  type        = string
  default     = "production"
}

variable "create_github_oidc_provider" {
  description = "Set to false if this AWS account already has the GitHub OIDC provider (only one is allowed)."
  type        = bool
  default     = true
}

variable "token_parameter_name" {
  description = "SSM Parameter Store SecureString holding INGEST_TOKEN. Create it yourself; it never enters Terraform state."
  type        = string
  default     = "/chesslens/ingest-token"
}

variable "alert_email" {
  description = "Email for budget and instance-health alerts."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget; alerts at 80% actual and 100% forecast."
  type        = number
  default     = 5
}

variable "http_ingress_cidrs" {
  description = "CIDR blocks allowed to reach port 80."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "use_elastic_ip" {
  description = "Attach an Elastic IP (stable address). Public IPv4 addresses are billed hourly, so this is off by default."
  type        = bool
  default     = false
}
