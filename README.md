# KamglobalAI EPMS

Enterprise Performance Management System (EPMS) built with Streamlit and SQLite.

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
- SQLite
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
