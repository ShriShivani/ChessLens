output "instance_id" {
  description = "EC2 instance ID (also the SSM target)."
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Address of the app."
  value       = var.use_elastic_ip ? aws_eip.app[0].public_ip : aws_instance.app.public_ip
}

output "app_url" {
  description = "Open this in a browser; use it as --server for the edge client."
  value       = "http://${var.use_elastic_ip ? aws_eip.app[0].public_ip : aws_instance.app.public_ip}"
}

output "github_deploy_role_arn" {
  description = "Store as the AWS_ROLE_ARN repository variable in GitHub."
  value       = aws_iam_role.github_deploy.arn
}
