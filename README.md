# KamglobalAI EPMS

Enterprise Performance Management System (EPMS) built with Streamlit; uses SQLite locally or PostgreSQL when `EPMS_DATABASE_URL` is set.

## Features

- Role-based login (`Admin`, `Manager`, `Employee`, `Viewer`)
- Dynamic KPI scorecard by Department and Role
- Weighted scoring engine with rating bands
- Workflow lifecycle (`Draft` -> `Submitted` -> `Manager Reviewed` -> `Calibrated` -> `Finalized`)
- Cycle controls (open/close review cycles)
- Team visibility controls
- Calibration panel (actual vs recommended distribution)
- Audit logs for important actions
- CSV and PDF export

## Tech Stack

- Python
- Streamlit
- SQLite or PostgreSQL (via SQLAlchemy)
- Plotly
- Pandas
- ReportLab

## Local Run

1. Open terminal in project root:

```powershell
cd c:\projects\kpi
```

2. Create and activate virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

3.1 Optional: configure environment file:

```powershell
copy .env.example .env
```

4. Run app:

```powershell
streamlit run app.py
```

5. Open:

- http://localhost:8501

## Default Login

- Username: `admin`
- Password: `Admin@123`

Change password immediately after first login.

## Production Notes

- Database file: `epms.db` (auto-created and migrated at startup)
- Keep regular backups of `epms.db`
- Use strong admin password and disable unused accounts
- For internet-facing deployment, place behind reverse proxy and HTTPS
- Configure environment variables for production-safe defaults:
  - `EPMS_DB_PATH` (default: `epms.db`)
  - `EPMS_DATABASE_URL` (optional, example: `postgresql+psycopg2://user:pass@host:5432/epms`)
  - `EPMS_ADMIN_USERNAME` (default: `admin`)
  - `EPMS_ADMIN_PASSWORD` (default: `Admin@123`)
  - Email (SMTP / AWS SES SMTP):
    - `EPMS_SMTP_HOST`, `EPMS_SMTP_PORT`, `EPMS_SMTP_USERNAME`, `EPMS_SMTP_PASSWORD`
    - `EPMS_EMAIL_FROM`, `EPMS_SMTP_STARTTLS`

## AWS Deployment (Recommended: RDS + ECS/Fargate + SES SMTP)

This app is container-ready (see `Dockerfile`). The common AWS production setup is:

- **RDS PostgreSQL** for persistence
- **ECS/Fargate** to run the Streamlit container
- **Application Load Balancer (ALB)** + **ACM** for HTTPS + custom domain
- **SES** for outgoing email (via SMTP)

### 1) Create RDS PostgreSQL

- **Engine**: PostgreSQL 15+ (any supported version is OK)
- **Public access**: No (recommended)
- **Security Group**:
  - Inbound: allow TCP `5432` from the **ECS task security group** only
- Note the endpoint, DB name, username, password.

Set `EPMS_DATABASE_URL` like:

`postgresql+psycopg2://USER:PASSWORD@RDS_ENDPOINT:5432/DBNAME`

### 2) Enable AWS SES (Email)

- Verify a sender identity (domain or email) in SES.
- Request production access if SES is in sandbox.
- Create **SMTP credentials** in SES (these are different from IAM keys).

Set:

- `EPMS_SMTP_HOST`: e.g. `email-smtp.us-east-1.amazonaws.com`
- `EPMS_SMTP_PORT`: `587`
- `EPMS_SMTP_USERNAME` / `EPMS_SMTP_PASSWORD`: from SES SMTP credentials
- `EPMS_EMAIL_FROM`: verified sender (e.g. `noreply@yourdomain.com`)
- `EPMS_SMTP_STARTTLS`: `true`

### 3) Push image to ECR

- Create an ECR repository (e.g. `kpi-epms`).
- Build and push:

```powershell
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com
docker build -t kpi-epms .
docker tag kpi-epms:latest <acct>.dkr.ecr.<region>.amazonaws.com/kpi-epms:latest
docker push <acct>.dkr.ecr.<region>.amazonaws.com/kpi-epms:latest
```

### 4) Create ECS/Fargate service

- **Cluster**: Fargate
- **Task definition**:
  - Container port: `8501`
  - Health check (ALB): path `/` (Streamlit responds with 200)
  - Logging: CloudWatch Logs
  - Environment variables (set in task definition), **do not use `.env` in production**:
    - `EPMS_DATABASE_URL`
    - `EPMS_ADMIN_USERNAME`, `EPMS_ADMIN_PASSWORD`, `EPMS_ENABLE_ADMIN_SEED`
    - `EPMS_SMTP_*` and `EPMS_EMAIL_FROM`
  - Prefer AWS Secrets Manager for DB password and SMTP password
- **Networking**:
  - Private subnets (recommended)
  - Security group inbound: allow `8501` from the ALB security group only

### 5) Add an ALB + HTTPS

- Create an **Application Load Balancer** in public subnets.
- Listener 80 → redirect to 443
- Listener 443 with **ACM** certificate for your domain
- Target group → ECS service port 8501
- Route53 record → ALB DNS

### 6) Verify and operate

- Watch logs in CloudWatch.
- Run DB migrations by simply starting the app (it auto-initializes schema).
- For updates: build/push new image → update ECS service to new task revision.
  - `EPMS_ENABLE_ADMIN_SEED` (`true`/`false`, default: `true`)

## Modular Structure

- `epms/auth.py` - password hashing and verification
- `epms/db.py` - DB init and schema management
- `epms/ui.py` - shared theme/branding styles
- `epms/reports.py` - PDF report generation

## CI

- GitHub Actions workflow at `.github/workflows/ci.yml`
- Runs on every push and pull request
- Installs dependencies and executes `pytest -q`

## AWS Deployment (Recommended For Internal Org Use)

### Target Pattern

- ECS Fargate (private subnets)
- Internal ALB
- Route53 private hosted zone (example: `epms.internal.kamglobalai.com`)
- Optional: access via VPN/Direct Connect only

### High-Level CLI Steps

1. Build and push image to ECR:

```bash
aws ecr create-repository --repository-name kamglobalai-epms
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker build -t kamglobalai-epms .
docker tag kamglobalai-epms:latest <account-id>.dkr.ecr.<region>.amazonaws.com/kamglobalai-epms:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/kamglobalai-epms:latest
```

2. Create ECS cluster/service (Fargate) and task definition with:
   - container port `8501`
   - env vars (`EPMS_DB_PATH` or `EPMS_DATABASE_URL`, etc.)
   - logs -> CloudWatch

3. Attach ECS service to an **internal** ALB target group.

4. Create Route53 private DNS record:
   - `epms.internal.kamglobalai.com` -> internal ALB DNS

5. (If public TLS endpoint needed) Use ACM certificate and HTTPS listener on ALB.

### DNS Mapping Checklist

- Domain managed in Route53 (or delegated DNS)
- Internal/private hosted zone created
- A/ALIAS record points to ALB
- Security groups allow only corporate CIDR/VPN ranges
- Health check path works (`/`)
- SSL cert attached (if HTTPS)

## Docker Run

1. Build image:

```bash
docker build -t kamglobalai-epms .
```

2. Run container:

```bash
docker run -p 8501:8501 -v epms_data:/app/data kamglobalai-epms
```

## Environment and Storage

- Default DB path is inside app folder.
- For persistent container storage, mount volume to `/app/data` and configure DB path if needed in future enhancement.

## Recommended Next Step

- Move DB path and secrets to environment variables (`.env`) for stronger production configuration.

## Testing

Run automated tests:

```powershell
pytest -q
```
