#!/usr/bin/env bash
# Установка «Парсер карт» на Ubuntu/Debian (VDSka VDS)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/parser-kart}"
APP_USER="${APP_USER:-parserkart}"

echo "==> Обновление пакетов"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip wget gnupg unzip

echo "==> Google Chrome (headless scraper)"
if ! command -v google-chrome >/dev/null 2>&1; then
  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
  sudo apt-get update -y
  sudo apt-get install -y google-chrome-stable
fi

echo "==> Пользователь и каталог"
sudo id -u "$APP_USER" >/dev/null 2>&1 || sudo useradd -r -m -d "$APP_DIR" -s /bin/bash "$APP_USER"
sudo mkdir -p "$APP_DIR"
sudo rsync -a --delete ./ "$APP_DIR/" --exclude .venv --exclude data/output
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Python venv"
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  sudo -u "$APP_USER" cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

echo "==> systemd"
sudo cp "$APP_DIR/deploy/parser-kart.service" /etc/systemd/system/parser-kart.service
sudo systemctl daemon-reload
sudo systemctl enable parser-kart
sudo systemctl restart parser-kart

echo "==> Готово. Проверка:"
curl -s "http://127.0.0.1:8000/api/health" || true
echo
echo "Откройте http://YOUR_SERVER_IP:8000 (или настройте nginx из deploy/nginx.conf)"
