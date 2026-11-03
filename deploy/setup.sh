#!/bin/sh
# Run on the VM as root after cloud-init: app user, venv, runner image, systemd unit. Idempotent.
set -eu
id cleanroom >/dev/null 2>&1 || useradd -m -s /bin/bash cleanroom
usermod -aG docker cleanroom
cd /opt && [ -d clean-room-intake ] || git clone https://github.com/chainwright/clean-room-intake.git
cd /opt/clean-room-intake && git pull --ff-only
docker build -t cleanroom-runner:1 sandbox/
python3 -m venv .venv && .venv/bin/pip install -q fastapi uvicorn openai python-multipart
chown -R cleanroom:cleanroom /opt/clean-room-intake
[ -f /etc/cleanroom.env ] || { echo "write /etc/cleanroom.env (VULTR_INFERENCE_KEY, CLEANROOM_MODEL) first"; exit 1; }
chmod 600 /etc/cleanroom.env
cat > /etc/systemd/system/cleanroom.service <<UNIT
[Unit]
Description=Clean Room Intake
After=docker.service
[Service]
User=cleanroom
WorkingDirectory=/opt/clean-room-intake
EnvironmentFile=/etc/cleanroom.env
ExecStart=/opt/clean-room-intake/.venv/bin/uvicorn app.web:app --host 127.0.0.1 --port 8080
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable --now cleanroom
# HTTPS: Caddy in front, certificate for <ip-with-dashes>.sslip.io
IP=$(curl -fs4 https://api.ipify.org || hostname -I | awk '{print $1}')
echo "CLEANROOM_HOST=$(echo "$IP" | tr . -).sslip.io" > /etc/default/caddy
cp deploy/Caddyfile /etc/caddy/Caddyfile
mkdir -p /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironmentFile=/etc/default/caddy\n' > /etc/systemd/system/caddy.service.d/env.conf
systemctl daemon-reload && systemctl restart caddy
echo "demo: https://$(echo "$IP" | tr . -).sslip.io"
