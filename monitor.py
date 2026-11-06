import csv
import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Lightweight fallback parser if python-dotenv is not installed
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as env_f:
            for line in env_f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

CONFIG_FILE = "config.json"
CSV_REPORT = f"report_{datetime.now().strftime('%Y-%m-%d')}.csv"
HTML_REPORT = f"report_{datetime.now().strftime('%Y-%m-%d')}.html"


def load_config():
    apis_list = []
    slack_url = ""
    email_config = {"enabled": False}
    openapi_source = ""
    apis_file = "apis.json"
    payload_overrides = {}

    # 1. Load general settings from config.json
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            slack_url = config.get("slack_webhook_url", "")
            email_config = config.get("email_alerts", {"enabled": False})
            openapi_source = config.get("openapi_source", "").strip()
            apis_file = config.get("apis_file", "apis.json")
            payload_overrides = config.get("payload_overrides", {})

    # Override/supplement secrets and settings with environment variables (.env)
    slack_url = os.environ.get("SLACK_WEBHOOK_URL", slack_url)
    if os.environ.get("EMAIL_ALERTS_ENABLED") is not None:
        email_config["enabled"] = os.environ.get("EMAIL_ALERTS_ENABLED", "").lower() in ("true", "1", "yes")
    if os.environ.get("SMTP_SERVER"):
        email_config["smtp_server"] = os.environ.get("SMTP_SERVER")
    if os.environ.get("SMTP_PORT"):
        try:
            email_config["smtp_port"] = int(os.environ.get("SMTP_PORT"))
        except ValueError:
            pass
    if os.environ.get("SENDER_EMAIL"):
        email_config["sender_email"] = os.environ.get("SENDER_EMAIL")
    if os.environ.get("SENDER_PASSWORD"):
        email_config["sender_password"] = os.environ.get("SENDER_PASSWORD")
    if os.environ.get("RECEIVER_EMAIL"):
        email_config["receiver_email"] = os.environ.get("RECEIVER_EMAIL")

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
        server_url = (
            servers[0].get("url", "") if servers else openapi_data.get("base_url", "")
        )

        # Handle relative or empty server URLs (e.g., servers: [{"url": "/api/v3"}])
        if server_url.startswith("http://") or server_url.startswith("https://"):
            base_url = server_url
        elif openapi_source.startswith("http://") or openapi_source.startswith("https://"):
            from urllib.parse import urlparse
            parsed_src = urlparse(openapi_source)
            origin = f"{parsed_src.scheme}://{parsed_src.netloc}"
            base_url = f"{origin.rstrip('/')}/{server_url.lstrip('/')}" if server_url else origin
        else:
            base_url = server_url

        paths = openapi_data.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                method_lower = method.lower()
                if method_lower in ["get", "post", "put", "delete", "patch"]:
                    formatted_path = (
                        path.replace("{petId}", "1")
                        .replace("{orderId}", "1")
                        .replace("{userId}", "1")
                        .replace("{username}", "user1")
                    )
                    full_url = base_url.rstrip("/") + "/" + formatted_path.lstrip("/")

                    # Smart query parameter resolution for required params
                    parameters = details.get("parameters", [])
                    query_parts = []
                    for param in parameters:
                        if param.get("in") == "query" and param.get("required"):
                            p_name = param.get("name")
                            p_schema = param.get("schema", {})
                            # Pick default enum or sample value
                            enums = p_schema.get("enum")
                            default_val = p_schema.get("default") or (enums[0] if enums else "available" if "status" in p_name else "tag1" if "tag" in p_name else "test")
                            query_parts.append(f"{p_name}={default_val}")

                    if query_parts:
                        connector = "&" if "?" in full_url else "?"
                        full_url += connector + "&".join(query_parts)

                    responses = details.get("responses", {})
                    # Broaden acceptable responses for lookups or updates
                    expected_status = 201 if "201" in responses else 200
                    expected_statuses = [expected_status]
                    if method_lower == "get" and "404" in responses:
                        expected_statuses.append(404)
                    if method_lower in ["post", "put"] and "400" in responses:
                        expected_statuses.append(400)

                    name = details.get("summary", f"{method.upper()} {path}")

                    # Determine payload:
                    # 1. Check explicit override from config.json
                    # 2. Schema-aware generation (array vs dict)
                    payload = None
                    if method_lower in ["post", "put", "patch"]:
                        if path in payload_overrides:
                            payload = payload_overrides[path]
                        else:
                            # Inspect schema in OpenAPI requestBody
                            req_body = details.get("requestBody", {})
                            content = req_body.get("content", {})
                            json_schema = content.get("application/json", {}).get("schema", {})
                            schema_type = json_schema.get("type", "object")

                            if schema_type == "array":
                                payload = [{"id": 1, "username": "user1"}]
                            else:
                                payload = {
                                    "id": 1,
                                    "name": "test_item",
                                    "photoUrls": ["https://example.com/item.jpg"],
                                    "status": "available",
                                }

                    apis_list.append(
                        {
                            "name": f"Docs: {name}",
                            "url": full_url,
                            "method": method.upper(),
                            "payload": payload,
                            "expected_status": expected_statuses[0] if len(expected_statuses) == 1 else expected_statuses,
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
                    "Method",
                    "URL",
                    "Status",
                    "Response Time (ms)",
                    "Response Body",
                    "Error",
                ]
            )
        writer.writerow(
            [
                result["timestamp"],
                result["name"],
                result["method"],
                result["url"],
                result["status"],
                result["response_time_ms"],
                result["response_body"],
                result["error"],
            ]
        )

def generate_html_report():
    import html as html_lib

    if not os.path.exists(CSV_REPORT):
        return

    html_content = (
        """
    <html>
    <head>
        <title>API Monitoring Report</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; margin: 20px; background: #f4f4f9; color: #333; }
            h2 { color: #222; }
            table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            th, td { padding: 10px; border: 1px solid #ddd; text-align: left; vertical-align: top; }
            th { background-color: #007bff; color: white; font-size: 14px; }
            .success { color: #28a745; font-weight: bold; }
            .failure { color: #dc3545; font-weight: bold; }
            .badge { display: inline-block; padding: 3px 7px; border-radius: 4px; font-weight: bold; font-size: 11px; font-family: monospace; }
            .badge-get { background: #e3f2fd; color: #0d47a1; }
            .badge-post { background: #e8f5e9; color: #1b5e20; }
            .badge-put { background: #fff3e0; color: #e65100; }
            .badge-delete { background: #ffebee; color: #b71c1c; }
            .badge-patch { background: #f3e5f5; color: #4a148c; }
            .response-box { max-height: 120px; max-width: 380px; overflow-y: auto; background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 4px; padding: 6px; font-family: monospace; font-size: 11px; white-space: pre-wrap; word-break: break-all; }
        </style>
    </head>
    <body>
        <h2>API Health Report - """
        + datetime.now().strftime("%Y-%m-%d")
        + """</h2>
        <table>
            <tr>
                <th style="width: 130px;">Timestamp</th>
                <th>API Name</th>
                <th style="width: 80px;">Method</th>
                <th>URL</th>
                <th style="width: 140px;">Status</th>
                <th style="width: 90px;">Latency</th>
                <th style="width: 380px;">Response Body</th>
                <th>Error Details</th>
            </tr>
    """
    )

    with open(CSV_REPORT, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Skip header
        for row in reader:
            if not row:
                continue
            # Backward compatibility check for 6-column vs 8-column format
            if len(row) >= 8:
                ts, name, method, url, status, latency, resp_body, err = (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                )
            else:
                ts, name, method, url, status, latency, resp_body, err = (
                    row[0],
                    row[1],
                    "GET",
                    row[2],
                    row[3],
                    row[4],
                    "",
                    row[5],
                )

            status_class = (
                "success" if "SUCCESS" in status or status == "200" else "failure"
            )
            badge_class = f"badge-{method.lower()}" if method else "badge-get"
            escaped_body = html_lib.escape(resp_body) if resp_body else "<span style='color:#888;'>None</span>"
            escaped_err = html_lib.escape(err)

            html_content += f"""
            <tr>
                <td>{ts}</td>
                <td><strong>{html_lib.escape(name)}</strong></td>
                <td><span class="badge {badge_class}">{method}</span></td>
                <td><a href="{html_lib.escape(url)}" target="_blank" style="color: #0366d6; text-decoration: none;">{html_lib.escape(url)}</a></td>
                <td class="{status_class}">{status}</td>
                <td>{latency} ms</td>
                <td><div class="response-box">{escaped_body}</div></td>
                <td style="color: #dc3545;">{escaped_err}</td>
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
        method = api.get("method", "GET").upper()
        payload = api.get("payload", None)  # <-- Extracted payload here
        expected_status = api["expected_status"]
        expected_key = api.get("expected_key", "")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_msg = ""
        status_result = "SUCCESS"
        response_time_ms = 0
        response_body = ""

        try:
            start_time = datetime.now()
            response = requests.request(
                method=method, url=url, json=payload, timeout=10
            )
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Capture response text (limit length for storage/display hygiene)
            if response.text:
                response_body = response.text[:1000]

            # Check HTTP Status Code (supports single int or list of acceptable codes)
            status_matched = (
                response.status_code in expected_status
                if isinstance(expected_status, list)
                else response.status_code == expected_status
            )
            if not status_matched:
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
                "method": method,
                "url": url,
                "status": status_result,
                "response_time_ms": response_time_ms,
                "response_body": response_body,
                "error": error_msg,
            }
        )

        # Trigger alerts if failed
        if "FAIL" in status_result:
            alert_text = (
                f"API *{name}* failed!\nMethod: {method}\nURL: {url}\nReason: {error_msg}\nTime:"
                f" {timestamp}"
            )
            send_slack_alert(config.get("slack_webhook_url"), alert_text)
            send_email_alert(
                config.get("email_alerts"), f"API Failure Alert: {name}", alert_text
            )
            print(f"❌ [FAIL] [{method}] {name} - {error_msg}")
        else:
            print(
                f"✅ [OK] [{method}] {name} responded in {response_time_ms}ms (Status:"
                f" {response.status_code})"
            )

    generate_html_report()
    print("Monitoring run completed. Reports updated.")

if __name__ == "__main__":
    run_monitor()
