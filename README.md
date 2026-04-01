# AIoT Smart Attendance & Door Lock System

> **اس پروجیکٹ کو اپنے لیپ ٹاپ پر چلانے کا مکمل گائیڈ نیچے موجود ہے۔**
> Complete guide to run this project on your laptop is provided below.

A face-recognition-based smart attendance and door-lock system built with **Django**, **OpenCV**, **dlib / face_recognition**, and **Arduino**.

---

## 🚀 System Overview

```
Webcam (Face Capture)
        ↓
  Python / Django
  (Face Recognition)
        ↓
   Arduino (Serial)
        ↓
  Servo Motor (Door)
        ↓
  Attendance Saved
        ↓
Email / Telegram Alert
```

---

## 🛠️ Requirements

### Hardware
| Component | Details |
|-----------|---------|
| Laptop / PC | Windows 10/11, Ubuntu 20.04+, or macOS |
| Webcam | Built-in or USB webcam |
| Arduino Uno | For door-lock control *(optional for laptop-only testing)* |
| PIR Motion Sensor | Connected to Arduino Pin 2 |
| Servo Motor | Connected to Arduino Pin 9 |
| USB Cable (Type-B) | To connect Arduino to laptop |

### Software
| Software | Version | Download |
|----------|---------|----------|
| Python | 3.9 or 3.10 *(recommended)* | https://www.python.org/downloads/ |
| Git | Latest | https://git-scm.com/ |
| Arduino IDE | 2.x | https://www.arduino.cc/en/software |
| VS Code *(optional)* | Latest | https://code.visualstudio.com/ |
| CMake | Bundled via pip | — |

> ⚠️ **Python 3.11+ may cause issues with `dlib`. Use Python 3.9 or 3.10.**

---

## ⚡ Installation – Step by Step

### Step 1 – Clone the Repository

```bash
git clone https://github.com/rizwansakhawat/aiot-smart-attendance-door-lock.git
cd aiot-smart-attendance-door-lock
```

---

### Step 2 – Create a Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

---

### Step 3 – Install Python Dependencies

```bash
pip install --upgrade pip
pip install django==4.2.7
pip install opencv-python==4.8.1.78
pip install numpy==1.24.3
pip install pyserial==3.5
pip install Pillow==10.1.0
pip install openpyxl==3.1.2
pip install cmake==3.27.7
pip install dlib-bin==19.24.6
pip install face-recognition==1.3.0 --no-deps
pip install django-environ==0.11.2
```

Or install everything at once (may require Visual C++ build tools on Windows):

```bash
pip install -r requirements.txt
```

> 💡 **Windows users:** If `dlib` installation fails, install
> [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
> and select *"Desktop development with C++"* before running pip install.

---

### Step 4 – Create the `.env` File

Create a file named **`.env`** in the project root (same folder as `manage.py`) with the following content:

```env
# Email settings (Gmail recommended)
EMAIL_HOST_USER=your_gmail@gmail.com
EMAIL_HOST_PASSWORD=your_app_password_here
ADMIN_EMAIL=your_gmail@gmail.com

# Telegram settings (optional – leave blank to disable)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

> 💡 **Gmail App Password:** Go to your Google Account → Security → 2-Step Verification → App Passwords → Generate a password for "Mail".

> 💡 **To disable email/Telegram**, just leave the values blank. The system will still work without notifications.

---

### Step 5 – Configure Arduino Port (if using hardware)

Open `smart_attendance_project/settings.py` and update the Arduino port:

```python
# Windows example:
ARDUINO_PORT = 'COM3'   # Check Device Manager for your port

# Linux example:
ARDUINO_PORT = '/dev/ttyUSB0'

# macOS example:
ARDUINO_PORT = '/dev/cu.usbmodem14201'
```

> 💡 If you **don't have Arduino hardware**, leave this as-is. The system will run in *software-only mode* and skip the serial connection.

---

### Step 6 – Apply Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

### Step 7 – Create a Superuser (Admin Account)

```bash
python manage.py createsuperuser
```

Enter your desired username, email, and password when prompted.

---

### Step 8 – Create the Static Files Folder

```bash
python manage.py collectstatic --noinput
```

---

## ▶️ Running the Project

### Run the Django Web Server

```bash
python manage.py runserver
```

Open your browser and go to:
```
http://127.0.0.1:8000/
```

Log in with the superuser credentials you created in Step 7.

---

### Run the Door System (Face Recognition + Arduino)

Open a **second terminal**, activate the virtual environment again, and run:

```bash
python door_system.py
```

This script:
- Opens the webcam
- Detects and recognizes faces
- Sends `UNLOCK` / `DENIED` commands to Arduino via serial
- Records attendance in the database
- Sends email / Telegram notifications

---

## 🔌 Arduino Setup

### Upload the Sketch

1. Open **Arduino IDE**.
2. Open the file `arduino_door_lock.ino` from this project folder.
3. Connect your Arduino Uno to the laptop via USB.
4. Select the correct **Board** (`Arduino Uno`) and **Port** (e.g., `COM3`) in *Tools* menu.
5. Click **Upload** (→ arrow button).

### Wiring

| Component | Arduino Pin |
|-----------|-------------|
| PIR Sensor (OUT) | Pin 2 |
| PIR Sensor (VCC) | 5V |
| PIR Sensor (GND) | GND |
| Servo Motor (Signal) | Pin 9 |
| Servo Motor (VCC) | 5V |
| Servo Motor (GND) | GND |

---

## 👤 Registering Students (Adding Faces)

1. Start the Django server (`python manage.py runserver`).
2. Go to `http://127.0.0.1:8000/` and log in as admin.
3. Navigate to **Students → Register Student**.
4. Fill in the student's name, roll number, department.
5. Use the **Capture Face** button to take a photo via webcam — this saves the face encoding automatically.

---

## 📂 Project Structure

```
aiot-smart-attendance-door-lock/
│
├── attendance/               # Django app (models, views, URLs)
│   └── services/             # Face recognition & notification services
├── smart_attendance_project/ # Django project settings & URLs
├── templates/                # HTML templates
├── door_system.py            # Face recognition + Arduino control script
├── arduino_door_lock.ino     # Arduino sketch
├── manage.py                 # Django management script
├── requirements.txt          # Python dependencies
└── .env                      # Secret keys & credentials (create manually)
```

---

## 🌐 Available Pages

| URL | Description |
|-----|-------------|
| `/` | Dashboard (admin or user view) |
| `/login/` | Login page |
| `/students/` | Student list (admin) |
| `/students/register/` | Register new student with face |
| `/attendance/` | Attendance records |
| `/reports/` | Export reports (Excel) |
| `/logs/` | System logs |
| `/admin/` | Django admin panel |

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| `dlib` install fails on Windows | Install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) and select *Desktop development with C++* |
| `No module named 'face_recognition'` | Run: `pip install face_recognition==1.3.0 --no-deps` |
| `ModuleNotFoundError: environ` | Run: `pip install django-environ` |
| Camera not opening | Check `CAMERA_INDEX = 0` in `settings.py`; try `1` for external webcam |
| Arduino port not found | Check Device Manager (Windows) or `ls /dev/tty*` (Linux/macOS) and update `ARDUINO_PORT` in `settings.py` |
| `.env` file not found error | Create `.env` in the project root (see Step 4) |
| `python manage.py migrate` fails | Make sure virtual environment is activated and dependencies are installed |
| Static files 404 errors | Run `python manage.py collectstatic --noinput` |

---

## 📋 Quick Start Summary

```bash
# 1. Clone and enter project
git clone https://github.com/rizwansakhawat/aiot-smart-attendance-door-lock.git
cd aiot-smart-attendance-door-lock

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file (see Step 4 above)

# 5. Apply migrations and create admin
python manage.py migrate
python manage.py createsuperuser

# 6. Run the web server
python manage.py runserver

# 7. (In a second terminal) Run the door/face system
python door_system.py
```

---

## 👨‍💻 Author

**Rizwan Sakhawat**

AIoT Smart Attendance & Door Lock System – Django + OpenCV + Arduino
