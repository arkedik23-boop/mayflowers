#!/usr/bin/env bash
# Установка и обновление бота May Flowers на сервере (Ubuntu 24.04).
# Запускается из deploy.bat. Повторный запуск безопасен: база не затирается.
set -euo pipefail
APP=/opt/mayflowers_bot
SERVICE=mayflowers-bot
cd "$APP"
sed -i 's/\r$//' .env server_install.sh mayflowers-bot.service 2>/dev/null || true
set -a; . ./.env; set +a
PORT="${PORT:-8090}"

echo "== Библиотеки для аудио/видео-открыток (QR-код, перекодирование голосовых)"
NEED=""
python3 -c "import qrcode, PIL" 2>/dev/null || NEED="$NEED python3-qrcode python3-pil"
command -v ffmpeg >/dev/null 2>&1 || NEED="$NEED ffmpeg"
if [ -n "$NEED" ]; then
  apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $NEED >/dev/null && echo "   установлено:$NEED"
else
  echo "   уже есть"
fi

echo "== Пользователь и папки"
id -u bot >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin bot
mkdir -p "$APP/data"
chown -R bot:bot "$APP"
chmod 600 "$APP/.env"

echo "== Служба $SERVICE"
cp "$APP/mayflowers-bot.service" /etc/systemd/system/$SERVICE.service
systemctl daemon-reload
systemctl enable $SERVICE >/dev/null 2>&1
systemctl restart $SERVICE
sleep 3
if ! systemctl is-active --quiet $SERVICE; then
  echo "!! Бот не запустился. Последние строки лога:"
  journalctl -u $SERVICE -n 30 --no-pager
  exit 1
fi
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null && echo "   бот работает, приём заказов на 127.0.0.1:$PORT"

echo "== HTTPS для мини-апки ($PUBLIC_HOST)"
if [ -z "${PUBLIC_HOST:-}" ]; then echo "   PUBLIC_HOST не задан, пропускаю"; exit 0; fi
BUSY=$(ss -ltnpH '( sport = :80 or sport = :443 )' 2>/dev/null | grep -v caddy || true)
if [ -n "$BUSY" ]; then
  echo "!! Порты 80/443 уже заняты другой программой (не Caddy), ничего не трогаю:"
  echo "$BUSY"
  echo "   Бот в Telegram работает. Чтобы заказы из мини-апки доходили, нужно настроить прокси на 127.0.0.1:$PORT вручную."
  exit 0
fi
if ! command -v caddy >/dev/null 2>&1; then
  apt-get update -qq
  if ! apt-get install -y -qq caddy >/dev/null 2>&1; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl gnupg >/dev/null
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy >/dev/null
  fi
fi
CF=/etc/caddy/Caddyfile
BLOCK="# mayflowers-begin
$PUBLIC_HOST {
	reverse_proxy 127.0.0.1:$PORT
}
# mayflowers-end"
if [ ! -f "$CF" ] || grep -q "/usr/share/caddy" "$CF"; then
  printf '%s\n' "$BLOCK" > "$CF"          # стандартный пустой Caddyfile заменяем целиком
elif grep -q "# mayflowers-begin" "$CF"; then
  sed -i '/# mayflowers-begin/,/# mayflowers-end/d' "$CF"; printf '\n%s\n' "$BLOCK" >> "$CF"
else
  cp "$CF" "$CF.bak.$(date +%s)"; printf '\n%s\n' "$BLOCK" >> "$CF"
fi
caddy validate --config "$CF" --adapter caddyfile >/dev/null
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi
systemctl enable caddy >/dev/null 2>&1; systemctl reload caddy 2>/dev/null || systemctl restart caddy
echo "   жду сертификат..."
for i in $(seq 1 30); do
  if curl -fsS "https://$PUBLIC_HOST/health" >/dev/null 2>&1; then echo "   HTTPS готов: https://$PUBLIC_HOST/health"; break; fi
  sleep 3
done
curl -fsS "https://$PUBLIC_HOST/health" >/dev/null 2>&1 || { echo "!! HTTPS пока не отвечает. Лог Caddy:"; journalctl -u caddy -n 20 --no-pager; }
echo "== Готово. Логи бота: journalctl -u $SERVICE -n 100"
