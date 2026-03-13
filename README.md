"# aiot-smart-attendance-door-lock" 
# EduTrack – Multi-Tenant Learning Management & Certification System

EduTrack is a **multi-tenant Learning Management System (LMS)** built with **Django** and **Django REST Framework (DRF)**.
It allows organizations to manage institutes, courses, enrollments, payments, and certificates in a scalable architecture.

The platform supports **role-based access**, **Stripe payment integration**, and **social authentication (Google + GitHub)**.

---

# 🚀 Features

## Authentication

* Email & Password Login
* Social Login (Google, GitHub, linkedin)
* JWT Authentication
* Role-Based Access Control

## Multi-Tenant Architecture

* Multiple organizations
* Organization admins
* Institute management per organization

## Course Management

* Instructors create courses
* Course pricing
* Institute-based courses

## Enrollment System

* Students enroll in courses
* Only **one enrollment per student per course**
* Enrollment status tracking

## Payment Integration

* Stripe checkout integration
* Secure payment processing
* Payment history tracking

## Certificate System

* Automatic certificate generation
* Course completion verification
* Downloadable certificates

---

# 🏗 System Architecture

```
User
   ↓
Organization
   ↓
Institute
   ↓
Course
   ↓
Enrollment
   ↓
Payment
   ↓
Certificate
```

---

# ⚙️ Tech Stack

Backend

* Django
* Django REST Framework

Database

* SQLite

Authentication

* JWT
* Django Allauth (Social Login)

Payments

* Stripe API

Tools

* Python
* Git
* VS Code

---

# 📂 Project Structure

```
edutrack/
│
├── users/            # User & roles
├── organizations/    # Organization management
├── core/             # Institute management
├── courses/          # Course module
├── enrollments/      # Student enrollment
├── payments/         # Stripe payment system
├── reports/          # Certificates
│
├── edutrack/         # Project settings
└── manage.py
```

---

# ⚡ Installation

## 1 Clone Repository

```bash
git clone https://github.com/yourusername/edutrack.git
cd edutrack
```

## 2 Create Virtual Environment

```bash
python -m venv venv
```

Activate environment

Windows

```bash
venv\Scripts\activate
```

Linux / Mac

```bash
source venv/bin/activate
```

---

## 3 Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4 Apply Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 5 Create Superuser

```bash
python manage.py createsuperuser
```

---

## 6 Run Server

```bash
python manage.py runserver
```

Server runs at:

```
http://127.0.0.1:8000/
```

---

# 🔗 API Endpoints

Main API root:

```
/api/
```

Available endpoints:

```
/user/
/organization/
/institute/
/courses/
/enrollment/
/payments/
/certificates/
```

---

# 💳 Payment Flow (Stripe)

```
Student
   ↓
Enroll in Course
   ↓
Stripe Checkout
   ↓
Payment Success
   ↓
Enrollment Activated
   ↓
Certificate Generated
```

---

# 👥 Roles

| Role       | Permissions                 |
| ---------- | --------------------------- |
| SuperAdmin | Manage organizations        |
| OrgAdmin   | Manage institutes           |
| Instructor | Create and manage courses   |
| Student    | Enroll and complete courses |

---

# 🔐 Security

* JWT Authentication
* Role-based permissions
* Secure Stripe payments
* Protected API endpoints

---

# 📌 Future Improvements

* Video lesson module
* Assignment system
* Progress tracking
* Email notifications
* Certificate PDF generation
* Analytics dashboard

---

# 👨‍💻 Author

**Rizwan**

EduTrack LMS Project – Django + DRF
