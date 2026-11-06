# API Health & Monitoring Service

An automated API health checking and reporting script for REST APIs and OpenAPI / Swagger specifications. It tests endpoints, generates HTML and CSV test reports, and sends alert notifications via Slack and Email when issues occur.

---

## 🚀 Features

- **OpenAPI / Swagger Integration**: Dynamically loads endpoints from live OpenAPI URLs (e.g. Swagger Petstore) or local specification files.
- **Automated Validation**: Sends method-appropriate HTTP requests (`GET`, `POST`, `PUT`, `DELETE`), generates default mock payloads based on schema types, and supports custom payload overrides.
- **Reporting**: Generates timestamped reports in both CSV and formatted HTML formats.
- **Alerting**: Real-time notifications via:
  - **Slack**: Webhook alerts with summary and failure details.
  - **Email (SMTP)**: Multi-part HTML/Plain text alert emails.
- **Secure Secret Management**: Separates secrets into `.env` (kept out of version control) while using `config.json` for general settings.

---

## 📋 Requirements

- Python 3.8+
- Packages: `requests`, `python-dotenv`

---

## 🛠️ Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd API_monitor
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install requests python-dotenv
   ```

4. **Configure Environment Variables**:
   Copy the example environment template and fill in your secrets:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your credentials:
   ```ini
   # Slack Alerts Configuration
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

   # Email Alerts Configuration
   EMAIL_ALERTS_ENABLED=true
   SMTP_SERVER=smtp.ethereal.email
   SMTP_PORT=587
   SENDER_EMAIL=your_email@example.com
   SENDER_PASSWORD=your_email_password
   RECEIVER_EMAIL=recipient@example.com
   ```

5. **Configure API Settings (`config.json`)**:
   General configuration is stored in `config.json`:
   ```json
   {
     "apis_file": "apis.json",
     "openapi_source": "https://petstore3.swagger.io/api/v3/openapi.json",
     "payload_overrides": {
       "/pet": {
         "id": 99991,
         "name": "HealthCheckPet",
         "photoUrls": ["https://example.com/pet.jpg"],
         "status": "available"
       }
     }
   }
   ```

---

## ▶️ Running the Monitor

Activate the virtual environment and run:
```bash
python monitor.py
```

### Generated Reports
After execution, reports are saved with timestamps:
- `report_YYYY-MM-DD.html`: Styled HTML report with pass/fail badges, response times, and error logs.
- `report_YYYY-MM-DD.csv`: Structured CSV report for data analysis and archiving.

---

## 🔒 Security Best Practices
- Never commit `.env` or sensitive credentials to Git.
- Keep `.env`, generated reports (`*.csv`, `*.html`), and log files in `.gitignore`.
