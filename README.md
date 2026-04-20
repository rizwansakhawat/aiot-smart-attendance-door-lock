# AIoT Smart Attendance Door Lock

An AIoT-based smart attendance and door lock system built with Django, face recognition, Arduino integration, and asynchronous notifications using Celery.

## What This Project Does

This project connects a Python/Django web app with a camera, Arduino, and face recognition. It can:

- recognize registered students or staff from a live camera feed
- mark attendance automatically
- unlock a physical door through Arduino and a servo motor
- show status on an LCD screen
- send alerts when an unknown person is detected
- let an admin control door modes from the web panel

## Features

- Face-recognition-based attendance marking
- Door control integration with Arduino
- Student registration and management
- Attendance reports and dashboards
- Asynchronous notifications via Celery
- Email and Telegram notification channels

## Hardware Used

- Arduino Uno
- PIR motion sensor for motion-triggered mode
- SG90 or similar servo motor for locking and unlocking
- 16x2 I2C LCD for status messages
- Green and red LEDs for door state indication
- USB camera for face recognition

## Arduino Integration

The Arduino sketch in [arduino_door_lock/arduino_door_lock.ino](arduino_door_lock/arduino_door_lock.ino) handles the physical side of the system:

- reads PIR sensor motion
- shows messages on the LCD
- opens and closes the servo lock
- turns LEDs on and off
- listens for serial commands from Python

Serial commands used by the project:

- `MOTION` - Arduino reports that motion was detected
- `UNLOCK:Name` - Python tells Arduino to unlock the door and show the name
- `LOCK` - close the door and return to waiting state
- `DENIED` / `DENIED_HOLD` - show unauthenticated/blocked message
- `IDLE` - return LCD to `Waiting for Motion...`
- `PING` - connection test

## Project Flow

1. The camera detects a face or motion.
2. Python compares the face against registered students.
3. If the person is recognized, Python sends `UNLOCK:Name` to Arduino.
4. Arduino unlocks the servo and shows the person's name on LCD.
5. If the person is unknown, Python sends denial commands and saves a snapshot.
6. Logs, attendance, and notifications are stored in Django.

## Operating Modes

- Mode 1: Live View
	- continuous face recognition only
- Mode 2: Live Attendance
	- attendance marking without Arduino
- Mode 3: Live Door Lock
	- camera + Arduino door control without PIR
- Mode 4: Full Mode
	- Arduino + camera + PIR motion trigger

## How to Use

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Configure environment

Create or update `.env` with database, email, Telegram, and secret key values.

### 3. Run migrations

```powershell
py .\manage.py migrate
```

### 4. Upload Arduino sketch

Open [arduino_door_lock/arduino_door_lock.ino](arduino_door_lock/arduino_door_lock.ino) in Arduino IDE and upload it to the board.

### 5. Start Django server

```powershell
py .\manage.py runserver
```

### 6. Open the control panel

Go to the Door Control panel and start the required mode.

### 7. Use the system

- For mode 3 or 4, the web panel can also send a manual `Open Door` command while the system is running.
- If an unknown person stays in view, the system shows an unauthorized state and returns to idle when the face disappears.

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
5. Upload the Arduino sketch to the board.

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

### Full system runtime

When you run `door_system.py`, it can operate in the following modes:

```powershell
py .\door_system.py 3
```

or

```powershell
py .\door_system.py 4
```

Use mode 3 for Arduino door lock without PIR, and mode 4 for the full PIR-triggered setup.

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

### Arduino not responding

- Make sure the sketch is uploaded to the board.
- Check that the correct COM port is available.
- Close Arduino IDE or other serial tools if the port is busy.

### Door panel starts but manual open does nothing

- Manual open only works when mode 3 or 4 is already running.
- Start one of those modes from the control panel first.

### Unknown person message keeps showing

- This is expected while the unknown face is still visible.
- The screen returns to `Waiting for Motion...` once the face is no longer detected.

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

# Run door system in Live Door Lock mode
py .\door_system.py 3

# Run door system in Full Mode
py .\door_system.py 4
```
