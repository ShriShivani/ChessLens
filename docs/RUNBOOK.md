# Runbook

Commands are PowerShell on Windows 11 unless noted. Run them from the repository root.

## 1. Run everything locally without Docker

```powershell
# one-time
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
cd web ; npm ci ; cd ..

# terminal 1: API (INGEST_TOKEN is the shared secret the edge client must send)
$env:INGEST_TOKEN = "dev-token"
.\.venv\Scripts\uvicorn server.main:app_factory --factory --port 8000

# terminal 2: web app (proxies /api and /ws to port 8000)
cd web ; npm run dev
```

Open http://localhost:5173.

## 2. Run everything locally with Docker

```powershell
Copy-Item .env.example .env        # then edit .env and set INGEST_TOKEN to a long random value
docker compose up --build
```

Open http://localhost:8080. The edge client talks to the same address
(`--server http://localhost:8080`). Data lives in the `chesslens-data` volume.

## 3. Operate the edge client

1. Phone as webcam. DroidCam: start the app on the phone and the DroidCam client on the PC,
   then the camera is usually index `0` or `1`. IP Webcam: use the URL it shows, for example
   `http://192.168.1.20:8080/video`.
2. Calibrate once per camera position (click the four board corners clockwise from top-left,
   press Enter):

   ```powershell
   python -m edge calibrate --source 0 --out calibration.json --white-side bottom
   ```

3. Track a game and broadcast it:

   ```powershell
   python -m edge run --source 0 --calibration calibration.json `
     --server http://localhost:8080 --token $env:INGEST_TOKEN --white "Ann" --black "Bo"
   ```

   It prints the viewer link. Without `--server` it works fully offline and only writes
   `game.pgn`.
4. Keys in the window: `u` undo, `f` set position from FEN, `m` force a move (SAN or UCI),
   `1`-`3` confirm a candidate when it says UNCERTAIN, `p` pause/resume, `x` flip, `n` new
   game, `q` quit.
5. If the board and the software disagree: press `u` (and play the real move with `m`), or
   `f` to type the position. Moves made while the network is down are sent automatically when
   it returns.

Replay a recorded video instead of a camera: `--source path\to\clip.mp4`.

## 4. Deploy to AWS (single small EC2 VM)

Do these in order. Nothing here is created automatically; you run each step yourself. See
[COSTS.md](COSTS.md) first.

### 4.1 Account and safety

1. Create the AWS account only now (the Free Plan lasts 6 months from signup).
2. Turn on MFA for the root user. Do not create access keys for it.
3. Check the current Free Plan terms and eligible instance types on the official AWS Free Tier
   page, and list eligible types for your region:

   ```powershell
   aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true --query "InstanceTypes[].InstanceType"
   ```

   If `t3.micro` is not listed, set `instance_type` in `terraform.tfvars` to one that is
   (keep an x86 type; the deploy script pulls x86 images).
4. Use an IAM Identity Center user or an admin IAM user with MFA for the CLI, and run
   `aws configure sso` (or `aws configure`) to set it up.

### 4.2 Secrets and variables

```powershell
# the shared ingest token (never goes into Terraform state)
$token = -join ((48..57)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
aws ssm put-parameter --name /chesslens/ingest-token --type SecureString --value $token
$token   # keep this: it is what --token on the edge client must be
```

### 4.3 Create the infrastructure

```powershell
cd infra
Copy-Item terraform.tfvars.example terraform.tfvars     # edit github_repo and alert_email
terraform init
terraform plan -out tfplan
# Review the plan. Then, and only then:
terraform apply tfplan
terraform output
```

Confirm the SNS subscription email AWS sends (otherwise the health alarm cannot reach you).
The AWS Budget emails need no confirmation.

### 4.4 Connect GitHub

1. Repository Settings > Environments > New environment `production`; add yourself under
   Required reviewers. This is the approval gate for deploys.
2. Repository Settings > Secrets and variables > Actions > Variables, add:
   `AWS_ROLE_ARN` (from `terraform output github_deploy_role_arn`), `AWS_REGION`,
   `EC2_INSTANCE_ID` (from `terraform output instance_id`), `PUBLIC_URL`
   (from `terraform output app_url`).
3. After the first run of the CD workflow has pushed images, open GitHub Packages and set
   `chesslens-server` and `chesslens-web` to public (or the VM cannot pull them).
4. Run the CD workflow (Actions > CD > Run workflow) and approve the deploy.

### 4.5 Verify

```powershell
curl http://<public_ip>/health
```

Then run an edge session with `--server http://<public_ip>` and open `http://<public_ip>`.

The site is plain HTTP, so the ingest token crosses the network unencrypted. Use it for demos
only, or put a TLS proxy (for example Cloudflare) in front. See ROADMAP.

### 4.6 Redeploy a specific version by hand

```powershell
aws ssm send-command --instance-ids <instance_id> --document-name AWS-RunShellScript `
  --parameters 'commands=["IMAGE_TAG=<git-sha> /opt/chesslens/deploy.sh"]'
```

## 5. Teardown (do this when you are done demoing)

1. Capture screenshots and the demo video first.
2. Tear down:

   ```powershell
   cd infra
   terraform destroy
   aws ssm delete-parameter --name /chesslens/ingest-token
   ```

3. In the AWS console confirm nothing is left: EC2 instances and volumes, Elastic IPs,
   CloudWatch alarms, SNS topics, Budgets. Delete the GitHub OIDC provider only if Terraform
   did not create it.
4. Remove the `AWS_*` and `EC2_INSTANCE_ID` variables from GitHub so the deploy job stays idle.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| Edge says "server unreachable" | URL, token, firewall; `curl <server>/health` |
| Viewer page says "Reconnecting" | Server down or proxy not forwarding `/ws/` (nginx config) |
| Game list empty | Edge was started without `--server`, or a different server |
| Moves keep coming up UNCERTAIN | Re-calibrate; reduce glare; make sure the camera has not moved |
| Nothing is detected | Board never "still": lower `--still`, check for flicker or moving background |
| `docker compose up` fails with INGEST_TOKEN error | Set it in `.env` |
| Deploy job skipped | `AWS_ROLE_ARN` variable not set |
| Deploy fails pulling images | GHCR packages still private |
| SSM command stuck | Instance profile or SSM agent; wait two minutes after first boot |
