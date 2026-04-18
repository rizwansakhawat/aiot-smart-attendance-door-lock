# AIoT Smart Attendance Door Lock

An AIoT-based smart attendance and door lock system built with Django, face recognition, Arduino integration, and asynchronous notifications using Celery.

## Features

- Face-recognition-based attendance marking
- Door control integration with Arduino
- Student registration and management
- Attendance reports and dashboards
- Asynchronous notifications via Celery
- Email and Telegram notification channels

## Project Structure

```text
aiot-smart-attendance-door-lock/
├── attendance/
│   ├── services/
│   │   ├── face_recognition_service.py
│   │   └── notification_service.py
│   ├── tasks.py
│   └── ...
├── smart_attendance_project/
│   ├── settings.py
│   ├── celery.py
│   └── ...
├── templates/
├── media/
├── door_system.py
├── test_notifications.py
├── requirements.txt
└── .env
```

## Requirements

- Python 3.10.11
- Redis (local or Docker)
- Windows 10/11 (tested)

## Setup

1. Create and activate virtual environment.
2. Install dependencies.
3. Configure environment variables.
4. Run migrations.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
```

## Environment Configuration

Use .env for all secrets and runtime settings.

### SMTP (email)

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=8
EMAIL_HOST_USER=your_email
EMAIL_HOST_PASSWORD=your_password_or_app_password
DEFAULT_FROM_EMAIL=Smart Attendance <your_email>
ADMIN_EMAIL=admin_email
```

### Telegram

```env
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_REQUEST_TIMEOUT=12
TELEGRAM_RETRY_ATTEMPTS=2
TELEGRAM_RETRY_DELAY_SECONDS=1
TELEGRAM_FAIL_COOLDOWN_SECONDS=50
```

### Celery

```env
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
CELERY_NOTIFICATIONS_ENABLED=True
```

## Run Redis

### Docker

```powershell
docker run -d --name redis -p 6379:6379 redis:7
```

## Run Application

### Django server

```powershell
python manage.py runserver
```

### Celery worker (Windows)

```powershell
celery -A smart_attendance_project worker -l info --pool=solo
```

## Test Notifications

Run notification test script:

```powershell
py .\test_notifications.py
```

Quick queue-only test:

```powershell
py .\test_notifications.py --no-wait
```

Increase result wait window if needed:

```powershell
$env:CELERY_TEST_TIMEOUT="180"
py .\test_notifications.py
```

## Notification Behavior

- If Telegram is disabled in settings, Telegram notifications are not sent.
- If SMTP is unreachable, email fails quickly using EMAIL_TIMEOUT.
- If Telegram repeatedly fails, cooldown prevents repeated long blocking attempts.

## Common Troubleshooting

### Tasks remain PENDING

- Make sure Redis is running.
- Make sure Celery worker is running.
- Check worker startup logs for broker URL.

### Email timeout or WinError 10060

- Usually network or VPN route is blocking SMTP ports.
- Test connectivity:

```powershell
Test-NetConnection smtp.gmail.com -Port 587
Test-NetConnection smtp.gmail.com -Port 465
```

### Telegram timeout

- Usually network route blocks api.telegram.org.
- Verify in browser: https://api.telegram.org
- Use VPN if required by your network region.

## Security Notes

- Do not commit .env to source control.
- Rotate credentials if they are ever exposed.
- Prefer provider API keys over account passwords where possible.

## Useful Commands

```powershell
# Start Redis
docker run -d --name redis -p 6379:6379 redis:7

# Restart Redis container
docker restart redis

# Stop and remove Redis container
docker rm -f redis

# Start Celery worker
celery -A smart_attendance_project worker -l info --pool=solo
```
