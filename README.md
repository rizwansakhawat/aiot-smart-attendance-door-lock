# AIoT Smart Attendance & Door Lock System

An **AI-powered Smart Attendance and Door Lock System** built with **Django**, **OpenCV**, and **Arduino**.  
The system uses **face recognition** to identify registered students/staff, automatically marks their attendance, unlocks the door, and sends **Email + Telegram notifications** — all in real time.

---

## 🚀 Features

* **Face Recognition** – Automatic identity verification using a webcam
* **Smart Door Lock** – Arduino-controlled servo motor unlocks on successful recognition
* **Attendance Tracking** – Attendance saved automatically to the database
* **Web Dashboard** – Admin and student dashboards to view records and reports
* **Email Notifications** – Attendance confirmation emails via Gmail
* **Telegram Notifications** – Instant Telegram alerts via a bot
* **Excel Reports** – Export attendance records as `.xlsx` files
* **Role-Based Access** – Separate admin and student login views
* **System Logs** – Full log history of all events

---

## 🏗 System Architecture

```
Person arrives at door
        ↓
PIR Motion Sensor (Arduino) detects motion
        ↓
Arduino sends MOTION:DETECTED to Python over USB serial
        ↓
Python captures webcam frame → Face Recognition
        ↓
     Known face?
    /           \
  YES             NO
   ↓               ↓
Save Attendance   Log denied attempt
Send UNLOCK       Send DENIED
  ↓
Arduino rotates servo → Door opens (5 sec) → Auto-locks
        ↓
Email + Telegram notification sent
```

---

## ⚙️ Tech Stack

| Layer            | Technology                            |
|------------------|---------------------------------------|
| Web Framework    | Django 4.2                            |
| Face Recognition | `face_recognition`, `dlib`, OpenCV    |
| Hardware         | Arduino Uno, PIR sensor, servo motor  |
| Serial Comm.     | PySerial                              |
| Database         | SQLite                                |
| Notifications    | Gmail SMTP, Telegram Bot API          |
| Reports          | openpyxl (Excel)                      |
| Language         | Python 3.10+                          |

---

## 🔧 Hardware Requirements

| Component        | Quantity | Notes                          |
|------------------|----------|--------------------------------|
| Arduino Uno      | 1        | Any USB-capable Arduino works  |
| PIR Motion Sensor| 1        | Connected to Pin 2             |
| Servo Motor      | 1        | Connected to Pin 9 (door lock) |
| USB Cable        | 1        | Arduino ↔ Laptop               |
| Webcam           | 1        | Built-in or external USB       |

---

## 💻 Laptop Setup – Complete Guide

### Step 1 — Prerequisites

Make sure the following are installed on your laptop:

* **Python 3.10 or 3.11** – [https://www.python.org/downloads/](https://www.python.org/downloads/)  
  ⚠️ During installation on Windows, check **"Add Python to PATH"**
* **Git** – [https://git-scm.com/downloads](https://git-scm.com/downloads)
* **Arduino IDE** – [https://www.arduino.cc/en/software](https://www.arduino.cc/en/software) (for uploading code to Arduino)
* **Visual Studio Build Tools** *(Windows only, required for dlib)*  
  Download from: [https://visualstudio.microsoft.com/visual-cpp-build-tools/](https://visualstudio.microsoft.com/visual-cpp-build-tools/)  
  During install select: **"Desktop development with C++"**

---

### Step 2 — Clone the Repository

```bash
git clone https://github.com/rizwansakhawat/aiot-smart-attendance-door-lock.git
cd aiot-smart-attendance-door-lock
```

---

### Step 3 — Create a Virtual Environment

```bash
python -m venv venv
```

Activate the environment:

**Windows (Command Prompt):**
```cmd
venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

You should see `(venv)` at the start of your terminal prompt.

---

### Step 4 — Install Dependencies

> ⚠️ `dlib` and `face_recognition` require a C++ compiler. Complete Step 1 first.

**Windows — recommended (pre-built wheel for dlib):**
```bash
pip install cmake
pip install dlib
pip install face-recognition --no-deps
pip install -r requirements.txt
```

**Linux / macOS:**
```bash
sudo apt-get install -y cmake libopenblas-dev liblapack-dev  # Ubuntu/Debian
pip install -r requirements.txt
```

> 💡 If `dlib` fails to compile, download the pre-built wheel from:  
> [https://github.com/jloh02/dlib/releases](https://github.com/jloh02/dlib/releases)  
> Choose the file matching your Python version — e.g. `dlib-19.24.6-cp310-cp310-win_amd64.whl` for Python 3.10  
> or `dlib-19.24.6-cp311-cp311-win_amd64.whl` for Python 3.11.  
> Then install it with `pip install dlib-19.24.6-cpXXX-cpXXX-win_amd64.whl`  
> (run `python --version` to confirm your Python version first)

---

### Step 5 — Configure Environment Variables

Create a `.env` file in the project root (same folder as `manage.py`):

```bash
# .env
EMAIL_HOST_USER=your.email@gmail.com
EMAIL_HOST_PASSWORD=your_gmail_app_password
ADMIN_EMAIL=admin@example.com

TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
TELEGRAM_CHAT_ID=your_chat_id
```

**How to get a Gmail App Password:**
1. Go to [https://myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification**
3. Search for **"App Passwords"** → create one for "Mail"
4. Use the generated 16-character password as `EMAIL_HOST_PASSWORD`

**How to get Telegram credentials:**
1. Message `@BotFather` on Telegram → `/newbot` → copy the token
2. Add the bot to your group/chat, then visit:  
   `https://api.telegram.org/bot<TOKEN>/getUpdates`  
   to find your `chat_id`

> 💡 If you do not want email/Telegram notifications, set in `settings.py`:  
> `NOTIFICATIONS_ENABLED = False`

---

### Step 6 — Configure Arduino Port

Open `smart_attendance_project/settings.py` and update the Arduino COM port:

```python
# Windows
ARDUINO_PORT = 'COM3'   # Change to your actual port (check Device Manager)

# Linux
ARDUINO_PORT = '/dev/ttyUSB0'  # or /dev/ttyACM0

# macOS
ARDUINO_PORT = '/dev/cu.usbmodem14101'
```

To find your Arduino port:
* **Windows** → Device Manager → Ports (COM & LPT)
* **Linux** → `ls /dev/tty*` before and after plugging in Arduino
* **macOS** → `ls /dev/cu.*`

---

### Step 7 — Apply Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

### Step 8 — Create an Admin Account

```bash
python manage.py createsuperuser
```

Enter a username, email, and password when prompted.

---

### Step 9 — Upload Code to Arduino

1. Open **Arduino IDE**
2. Open the file `arduino_door_lock.ino`
3. Go to **Tools → Board → Arduino Uno**
4. Go to **Tools → Port** → select your Arduino's COM port
5. Click **Upload** (→ arrow button)
6. Open **Serial Monitor** (baud rate: 9600) — you should see:
   ```
   AIoT Smart Door Lock System Started
   STATUS:READY
   ```

---

### Step 10 — Run the Django Web Server

```bash
python manage.py runserver
```

Open your browser and go to:

```
http://127.0.0.1:8000/
```

Log in with the superuser credentials you created in Step 8.

---

### Step 11 — Register Students/Staff (Face Enrollment)

1. Log in to the web dashboard as admin
2. Go to **Students → Register New Student**
3. Fill in the name, roll number, department
4. Use the webcam capture button to take a face photo
5. Save the record — the face encoding is stored automatically

---

### Step 12 — Run the Door System

Open a **second terminal** (keep Django server running in the first):

```bash
# Activate virtual environment first
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/macOS

python door_system.py
```

The system will:
* Connect to the webcam and Arduino
* Wait for PIR motion detection
* Capture face → recognize → unlock/deny
* Save attendance and send notifications

> 💡 You can run the system **without Arduino** for testing (it will operate in camera-only mode).

---

### Step 13 — Test Notifications

```bash
python test_notifications.py
```

This verifies that Email and Telegram notifications are working correctly.

---

## 📂 Project Structure

```
aiot-smart-attendance-door-lock/
│
├── arduino_door_lock.ino        # Arduino firmware (C++)
├── door_system.py               # Main door control script (Python)
├── manage.py                    # Django management
├── requirements.txt             # Python dependencies
├── test_notifications.py        # Notification test script
├── .env                         # Secret credentials (not committed)
│
├── smart_attendance_project/    # Django project settings
│   ├── settings.py
│   └── urls.py
│
├── attendance/                  # Main Django app
│   ├── models.py                # Student, Attendance, SystemLog, Department
│   ├── views.py                 # Web page views and API endpoints
│   ├── urls.py                  # URL routing
│   ├── admin.py                 # Django admin configuration
│   └── services/
│       ├── face_recognition_service.py   # Face encoding & matching
│       └── notification_service.py       # Email & Telegram alerts
│
├── templates/                   # HTML templates
│   └── attendance/
│
├── media/                       # Uploaded face photos (auto-created)
└── static/                      # CSS, JS, images
```

---

## 🌐 Web Dashboard Pages

| URL                         | Description                     | Access       |
|-----------------------------|---------------------------------|--------------|
| `/`                         | Dashboard (auto-redirects)      | All users    |
| `/login/`                   | Login page                      | Public       |
| `/students/`                | Student list                    | Admin only   |
| `/students/register/`       | Register new student            | Admin only   |
| `/attendance/`              | Attendance records              | All users    |
| `/reports/`                 | Generate Excel reports          | Admin only   |
| `/logs/`                    | System logs                     | Admin only   |
| `/profile/`                 | User profile                    | All users    |

---

## 🔐 Security Notes

* The `.env` file contains secrets — it is listed in `.gitignore` and must **never** be committed
* `DEBUG = True` is set for development only — set it to `False` in production
* The `SECRET_KEY` in `settings.py` should be changed for any public deployment

---

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| `dlib` fails to install | Install Visual Studio C++ Build Tools (Windows) or `build-essential` (Linux) |
| `face_recognition` import error | Install with `pip install face-recognition --no-deps` |
| Camera not found | Check `CAMERA_INDEX = 0` in `door_system.py`; try `1` or `2` for external webcam |
| Arduino not detected | Check COM port in Device Manager; update `ARDUINO_PORT` in `settings.py` |
| `.env` file not found | Create `.env` in the same directory as `manage.py` |
| Email not sending | Use a Gmail **App Password**, not your regular Gmail password |
| Telegram not working | Verify bot token and chat ID; make sure the bot is added to the chat |
| `ModuleNotFoundError: environ` | Run `pip install django-environ` |
| Migrations error | ⚠️ **Development only** — Delete `db.sqlite3` and all files in `attendance/migrations/` (except `__init__.py`), then re-run `makemigrations` and `migrate`. **Do not do this in production** as it will delete all data |

---

## 👨‍💻 Author

**Rizwan Sakhawat**  
AIoT Smart Attendance & Door Lock System — Django + OpenCV + Arduino
