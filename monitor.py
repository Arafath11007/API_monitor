import csv
import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

CONFIG_FILE = "config.json"
CSV_REPORT = f"report_{datetime.now().strftime('%Y-%m-%d')}.csv"
HTML_REPORT = f"report_{datetime.now().strftime('%Y-%m-%d')}.html"


def load_config():
    apis_list = []
    slack_url = ""
    email_config = {"enabled": False}
    openapi_source = ""
    apis_file = "apis.json"

    # 1. Load general settings from config.json
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            slack_url = config.get("slack_webhook_url", "")
            email_config = config.get("email_alerts", {"enabled": False})
            openapi_source = config.get("openapi_source", "").strip()
            apis_file = config.get("apis_file", "apis.json")

    # 2. Determine source based on openapi_source value
    openapi_data = None

    if openapi_source:
        if openapi_source.startswith("http://") or openapi_source.startswith(
            "https://"
        ):
            try:
                print(f"🌐 Fetching live API docs from: {openapi_source}...")
                response = requests.get(openapi_source, timeout=10)
                if response.status_code == 200:
                    openapi_data = response.json()
            except Exception as e:
                print(f"⚠️ Could not fetch live OpenAPI specs: {e}")
        else:
            if os.path.exists(openapi_source):
                print(f"📖 Reading API docs from local file: {openapi_source}...")
                with open(openapi_source, "r") as f:
                    openapi_data = json.load(f)
            else:
                print(f"⚠️ Local file '{openapi_source}' not found.")

    # 3. Parse OpenAPI data if loaded (from URL or local docs file)
    if openapi_data:
        servers = openapi_data.get("servers", [])
        base_url = (
            servers[0].get("url", "") if servers else openapi_data.get("base_url", "")
        )

        paths = openapi_data.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() in ["get", "post", "put", "delete", "patch"]:
                    formatted_path = (
                        path.replace("{petId}", "1")
                        .replace("{orderId}", "1")
                        .replace("{userId}", "1")
                    )
                    full_url = base_url.rstrip("/") + formatted_path

                    responses = details.get("responses", {})
                    expected_status = 201 if "201" in responses else 200
                    name = details.get("summary", f"{method.upper()} {path}")

                    apis_list.append(
                        {
                            "name": f"Docs: {name}",
                            "url": full_url,
                            "method": method.upper(),
                            "payload": (
                                {"name": "test_item", "status": "available"}
                                if method.lower() in ["post", "put", "patch"]
                                else None
                            ),
                            "expected_status": expected_status,
                            "expected_key": "",
                        }
                    )
    else:
        # Fallback to loading standard apis.json if openapi_source is blank or failed
        if os.path.exists(apis_file):
            print(f"📁 Reading custom endpoints from local file ({apis_file})...")
            with open(apis_file, "r") as f:
                api_data = json.load(f)
                apis_list.extend(api_data.get("apis", []))

    return {
        "apis": apis_list,
        "slack_webhook_url": slack_url,
        "email_alerts": email_config,
    }


def send_slack_alert(webhook_url, message):
    if not webhook_url or "YOUR_SLACK" in webhook_url:
        return
    payload_data = {"text": f"🚨 *API Monitor Alert*\n{message}"}
    try:
        requests.post(webhook_url, json=payload_data)
    except Exception as e:
        print(f"Failed to send Slack alert: {e}")


def send_email_alert(email_config, subject, body):
    if not email_config.get("enabled"):
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = email_config["sender_email"]
        msg["To"] = email_config["receiver_email"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"])
        server.starttls()
        server.login(email_config["sender_email"], email_config["sender_password"])
        server.sendmail(
            email_config["sender_email"],
            email_config["receiver_email"],
            msg.as_string(),
        )
        server.quit()
    except Exception as e:
        print(f"Failed to send email alert: {e}")


def log_result(result):
    file_exists = os.path.exists(CSV_REPORT)
    with open(CSV_REPORT, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "Timestamp",
                    "API Name",
                    "URL",
                    "Status",
                    "Response Time (ms)",
                    "Error",
                ]
            )
        writer.writerow(
            [
                result["timestamp"],
                result["name"],
                result["url"],
                result["status"],
                result["response_time_ms"],
                result["error"],
            ]
        )


def generate_html_report():
    if not os.path.exists(CSV_REPORT):
        return

    html_content = (
        """
    <html>
    <head>
        <title>API Monitoring Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f4f4f9; }
            h2 { color: #333; }
            table { width: 100%; border-collapse: collapse; background: white; }
            th, td { padding: 10px; border: 1px solid #ddd; text-align: left; }
            th { background-color: #007bff; color: white; }
            .success { color: green; font-weight: bold; }
            .failure { color: red; font-weight: bold; }
        </style>
    </head>
    <body>
        <h2>API Health Report - """
        + datetime.now().strftime("%Y-%m-%d")
        + """</h2>
        <table>
            <tr>
                <th>Timestamp</th>
                <th>API Name</th>
                <th>URL</th>
                <th>Status</th>
                <th>Response Time (ms)</th>
                <th>Error Details</th>
            </tr>
    """
    )

    with open(CSV_REPORT, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            status_class = (
                "success" if "SUCCESS" in row[3] or row[3] == "200" else "failure"
            )
            html_content += f"""
            <tr>
                <td>{row[0]}</td>
                <td>{row[1]}</td>
                <td>{row[2]}</td>
                <td class="{status_class}">{row[3]}</td>
                <td>{row[4]}</td>
                <td>{row[5]}</td>
            </tr>
            """

    html_content += """
        </table>
    </body>
    </html>
    """

    with open(HTML_REPORT, "w", encoding="utf-8") as f:
        f.write(html_content)


def run_monitor():
    config = load_config()
    if not config:
        return

    print(f"[{datetime.now()}] Starting API health check...")

    for api in config.get("apis", []):
        name = api["name"]
        url = api["url"]
        method = api.get("method", "GET")
        payload = api.get("payload", None)  # <-- Extracted payload here
        expected_status = api["expected_status"]
        expected_key = api.get("expected_key", "")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_msg = ""
        status_result = "SUCCESS"
        response_time_ms = 0

        try:
            start_time = datetime.now()
            response = requests.request(
                method=method, url=url, json=payload, timeout=10
            )
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Check HTTP Status Code
            if response.status_code != expected_status:
                status_result = f"FAIL (Code: {response.status_code})"
                error_msg = (
                    f"Expected status {expected_status}, got {response.status_code}"
                )

            # Check JSON and expected key if specified
            elif expected_key:
                try:
                    data = response.json()
                    if expected_key not in data:
                        status_result = "FAIL (Key Missing)"
                        error_msg = f"Key '{expected_key}' not found in JSON response"
                except ValueError:
                    if response.text.strip():
                        status_result = "FAIL (Invalid JSON)"
                        error_msg = "Response is not valid JSON"

        except requests.exceptions.Timeout:
            status_result = "FAIL (Timeout)"
            error_msg = "Request timed out after 10 seconds"
        except requests.exceptions.ConnectionError:
            status_result = "FAIL (Connection Error)"
            error_msg = "Could not connect to server"
        except Exception as e:
            status_result = "FAIL (Exception)"
            error_msg = str(e)

        # Log to CSV
        log_result(
            {
                "timestamp": timestamp,
                "name": name,
                "url": url,
                "status": status_result,
                "response_time_ms": response_time_ms,
                "error": error_msg,
            }
        )

        # Trigger alerts if failed
        if "FAIL" in status_result:
            alert_text = (
                f"API *{name}* failed!\nURL: {url}\nReason: {error_msg}\nTime:"
                f" {timestamp}"
            )
            send_slack_alert(config.get("slack_webhook_url"), alert_text)
            send_email_alert(
                config.get("email_alerts"), f"API Failure Alert: {name}", alert_text
            )
            print(f"❌ [FAIL] {name} - {error_msg}")
        else:
            print(
                f"✅ [OK] {name} responded in {response_time_ms}ms (Status:"
                f" {response.status_code})"
            )

    generate_html_report()
    print("Monitoring run completed. Reports updated.")


if __name__ == "__main__":
    run_monitor()
