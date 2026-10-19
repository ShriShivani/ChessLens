# Costs

Estimates only. Prices are list prices as I understand them for us-east-1 and they change;
check the AWS pricing pages and the Free Tier page before relying on any number here.

## Local use

$0. Everything (edge, server, web, Docker) runs on your own machine.

## GitHub

$0 for public repositories (Actions minutes and GHCR storage within the free limits).

## AWS (only if you deploy)

| Item | Approx. monthly | Note |
|---|---|---|
| EC2 t3.micro, running 24/7 | about $7.60 | Free Plan eligible on new accounts; verify for your region |
| 8 GB gp3 root volume | about $0.65 | |
| Public IPv4 address | about $3.65 | Charged per hour even when attached; there is no Elastic IP by default |
| SNS email alerts, AWS Budgets, basic CloudWatch metrics | about $0 | Within free allowances |
| Data transfer | about $0 | Tiny: only move events and a static page |
| **Total if it ran all month** | **about $12** | |

New accounts created on or after 2025-07-15 get $100 of credits and can earn $100 more.
On the Free Plan the account stops being usable after 6 months or when credits run out,
whichever comes first, and its resources are lost. A demo that runs a few days costs
a few dollars of credits at most, and `terraform destroy` stops all charges.

Deliberately not used (the usual surprise bills): NAT gateway, load balancer, RDS, Fargate,
CloudFront (optional later).

## Protection

- AWS Budget alert at 80% of actual and 100% of forecast spend (default budget $5).
- Health alarm emails you if the instance stops responding.
- Everything is in Git and Terraform; `terraform destroy` removes it.
