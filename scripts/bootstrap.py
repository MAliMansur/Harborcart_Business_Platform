#!/usr/bin/env python3
"""Create local-only settings without overwriting existing secrets or data."""
import os
import secrets
from pathlib import Path
root = Path(__file__).resolve().parent.parent
local = root / ".local"
local.mkdir(exist_ok=True)
os.chmod(local, 0o700)
env = root / ".env"
if env.exists():
    print("Existing .env preserved. Existing credentials and data are unchanged.")
else:
    password = secrets.token_urlsafe(18)
    token = secrets.token_urlsafe(36)
    database_password = secrets.token_urlsafe(30)
    settings = {
        "HC_ENV": "local", "ENABLE_DEMO": "1",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(60), "METRICS_TOKEN": token,
        "DEMO_PASSWORD": password, "POSTGRES_PASSWORD": database_password,
        "POSTGRES_APP_PASSWORD": secrets.token_urlsafe(30),
        "POSTGRES_TEST_PASSWORD": secrets.token_urlsafe(30),
        "GRAFANA_PASSWORD": secrets.token_urlsafe(24),
        "ALLOWED_HOSTS": "localhost,127.0.0.1,[::1],web,testserver",
        "CSRF_TRUSTED_ORIGINS": "http://localhost:8080,http://127.0.0.1:8080",
    }
    with env.open("x") as f:
        os.chmod(env, 0o600)
        f.write("# Local exercise secrets. Never commit this file.\n")
        f.write("".join(key + "=" + value + "\n" for key, value in settings.items()))
    credentials = local / "demo-credentials.txt"
    with credentials.open("x") as f:
        os.chmod(credentials, 0o600)
        f.write("LOCAL EXERCISE ACCOUNTS — same generated password, no real customer data\n")
        f.write("Workspace: Atlas Supply\n")
        for username, role in [("buyer","Buyer"),("manager","Purchasing manager"),
                               ("warehouse","Warehouse operator"),("finance","Finance analyst"),
                               ("operator","Workspace administrator")]:
            f.write(username + " — " + role + "\n")
        f.write("Other workspace: rival (buyer), rival-manager (manager)\n")
        f.write("Password: " + password + "\n")
    with (local / "metrics-token").open("x") as f:
        # Prometheus container's unprivileged user must read this bind mount.
        f.write(token)
    os.chmod(local / "metrics-token", 0o644)
    print("Local secrets created. Read .local/demo-credentials.txt privately.")
    print("Start with make install, make setup, then make run and make worker.")
