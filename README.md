# AIoT Smart Attendance Door Lock

An end-to-end AIoT access control and attendance platform built with Django, OpenCV face recognition, Arduino hardware control, and asynchronous notifications via Celery.

## Executive Overview

This project combines software intelligence and physical automation to deliver secure, auditable, and real-time entry control.

Core outcomes:

- automatic attendance marking for recognized users
- real door unlock and lock control through Arduino and a servo motor
- live visual status through LCD and LEDs
- unknown-person alerting with snapshot capture
- centralized control and monitoring from a web dashboard

## End-to-End Flow

1. Video is captured from a connected camera.
2. Face recognition matches the current face against registered identities.
3. If a valid match is confirmed, the system:
	 - records attendance
	 - sends `UNLOCK:Name` to Arduino
	 - opens the door and displays user feedback on LCD
4. If the face remains unknown beyond the configured threshold, the system:
	 - keeps access blocked
	 - stores an image snapshot
	 - raises admin alerts (email/Telegram)
5. All outcomes are persisted through logs and attendance records for traceability.

## System Capabilities

- face-recognition-based attendance automation
- Arduino-driven physical door control
- live camera preview and operational modes from admin panel
- unknown-person detection and alert pipeline
- asynchronous notification delivery with Celery workers
- reporting and operational visibility via Django dashboards

## Face Recognition Model (Viva Quick Answer)

**Exact stack used in this project**
- `face-recognition==1.3.0`
- `face_recognition_models==0.3.0`
- `dlib-bin==19.24.6`
- `opencv-python==4.8.1.78` (camera/frame preprocessing, not embedding model)

**Model and architecture**
- Face detection in `attendance/services/face_recognition_service.py` uses `face_recognition.face_locations(..., model='hog')` by default.
- Face embedding uses dlib's pre-trained **ResNet-based face recognition model** (128-dimensional embedding) exposed through `face_recognition.face_encodings(...)`.
- Matching is done with Euclidean distance via `face_recognition.face_distance(...)`.

**How it is used in this codebase**
- Registered students' embeddings are loaded and averaged (`load_registered_faces`, `calculate_average_encoding`).
- For each live frame, system detects face → generates unknown embedding → computes distances with cached embeddings (`recognize_face`).
- Best match is selected using `np.argmin(face_distances)`.

**Key thresholds/parameters**
- `FACE_RECOGNITION_TOLERANCE = 0.42` (settings)
- `FACE_RECOGNITION_MIN_CONFIDENCE = 0.58`
- `FACE_RECOGNITION_MIN_GAP = 0.04`
- `FACE_RECOGNITION_CONFIRM_FRAMES = 2`
- `FACE_RECOGNITION_CONFIRM_WINDOW_SECONDS = 1.5`
- `FACE_RECOGNITION_UPSAMPLE = 1`

**Why this model was chosen (project context)**
- Practical CPU-friendly pipeline for real-time door lock decisions.
- Mature Python integration (Django + OpenCV + face_recognition).
- 128-D embeddings + distance thresholding are simple to tune and deploy on edge-style systems.

**Viva comparison with alternatives**
- vs OpenCV classical recognizers (LBPH/Eigenfaces): dlib embeddings are generally more robust to pose/lighting changes.
- vs deep alternatives like FaceNet/ArcFace: those can be more accurate at scale, but usually need heavier training/inference stack and deployment complexity.
- Current project prioritizes **deployment simplicity + real-time responsiveness** over state-of-the-art benchmark accuracy.

## Hardware Layer

- Arduino Uno
- PIR motion sensor (for full motion-triggered mode)
- SG90 (or equivalent) servo motor
- 16x2 I2C LCD display
- red/green status LEDs
- USB camera

## Arduino and Serial Protocol

The Arduino firmware is located at [arduino_door_lock/arduino_door_lock.ino](arduino_door_lock/arduino_door_lock.ino).

Arduino responsibilities:

- motion sensing (PIR)
- servo actuation for lock/unlock
- LCD feedback rendering
- LED state control
- serial communication with Python controller

Primary serial commands:

- `MOTION` - motion event emitted by Arduino
- `UNLOCK:Name` - unlock door and show user name
- `LOCK` - return to secure/locked state
- `DENIED` and `DENIED_HOLD` - unauthorized access state
- `IDLE` - restore waiting display
- `PING` - connectivity check

## Operating Modes

- Mode 1: Live View
	- continuous recognition display only
- Mode 2: Live Attendance
	- attendance automation without Arduino dependency
- Mode 3: Live Door Lock
	- continuous camera + Arduino control (no PIR trigger required)
- Mode 4: Full Mode
	- Arduino + camera + PIR-triggered recognition workflow

## Project Structure

```text
aiot-smart-attendance-door-lock/
├── attendance/
│   ├── services/
│   │   ├── face_recognition_service.py
│   │   └── notification_service.py
│   ├── tasks.py
│   └── ...
├── door_control/
│   ├── views.py
│   ├── urls.py
│   └── templates/door_control/control.html
├── smart_attendance_project/
│   ├── settings.py
│   ├── celery.py
│   └── ...
├── arduino_door_lock/
│   └── arduino_door_lock.ino
├── media/
│   └── runtime/
├── door_system.py
├── manage.py
├── requirements.txt
└── .env
```

## Requirements

- Python 3.10.11
- Redis (local or Docker)
- Windows 10/11 (validated)
- Arduino IDE (for firmware upload)

## Installation and Setup

1. Create and activate virtual environment.
2. Install dependencies.
3. Configure environment variables.
4. Run database migrations.
5. Upload Arduino firmware.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
```

## Environment Configuration

Use `.env` for secrets and runtime parameters.

### SMTP (Email)

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

### Celery / Redis

```env
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
CELERY_NOTIFICATIONS_ENABLED=True
```

## Running the System

### Start Redis

```powershell
docker run -d --name redis -p 6379:6379 redis:7
```

### Start Django

```powershell
python manage.py runserver
```

### Start Celery Worker (Windows)

```powershell
celery -A smart_attendance_project worker -l info --pool=solo
```

### Start Door Runtime (Direct CLI)

```powershell
py .\door_system.py 3
```

or

```powershell
py .\door_system.py 4
```

### Start Door Runtime (Web Panel)

Open the Door Control panel and start mode 3 or mode 4.

Manual door open from panel:

- supported while mode 3 or 4 is active
- sends an open command to the currently running door process

## Operational Notes

- Unknown-person states remain active while the unknown face is continuously visible.
- Once the unknown face disappears, the system transitions back to idle waiting state.
- All key events are logged for review in dashboards and system logs.

## Troubleshooting

### Arduino not responding

- confirm firmware upload to Arduino board
- verify COM port availability
- close any process holding serial port (Arduino IDE, monitor tools)

### Manual Open button does not unlock

- ensure mode 3 or 4 is already running
- ensure Arduino connection is healthy in the active runtime

### Celery tasks remain pending

- verify Redis is running
- verify Celery worker is running
- verify broker URL in environment variables

### SMTP timeout / WinError 10060

- verify SMTP route and network policy
- test ports using:

```powershell
Test-NetConnection smtp.gmail.com -Port 587
Test-NetConnection smtp.gmail.com -Port 465
```

### Telegram timeout

- verify outbound access to `api.telegram.org`
- test with browser connectivity
- use VPN if required by local network policy

## Security Practices

- never commit `.env` to source control
- rotate exposed credentials immediately
- prefer app passwords or scoped API keys over primary account credentials

## Useful Commands

```powershell
# Redis
docker run -d --name redis -p 6379:6379 redis:7
docker restart redis
docker rm -f redis

# Celery
celery -A smart_attendance_project worker -l info --pool=solo

# Door runtime
py .\door_system.py 3
py .\door_system.py 4

# Notification tests
py .\test_notifications.py
py .\test_notifications.py --no-wait
```
