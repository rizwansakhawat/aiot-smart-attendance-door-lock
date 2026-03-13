"# aiot-smart-attendance-door-lock" 
EduTrack – Multi-Tenant Learning Management & Certification System

EduTrack is a multi-tenant Learning Management System (LMS) built with Django and Django REST Framework.
It allows organizations to manage institutes, courses, student enrollments, payments, and certificates in a scalable way.

The system supports role-based access, Stripe payments, and social authentication.

Features
Authentication

Email/Password Login

Social Authentication (Google, GitHub)

JWT Authentication

Role-based access control

Multi-Tenant Architecture

Multiple organizations

Organization admins

Isolated institute management

Course Management

Create and manage courses

Instructor-based course creation

Course pricing and details

Enrollment System

Students enroll in courses

One enrollment per course per student

Track course progress

Payment Integration

Stripe payment gateway

Secure checkout sessions

Payment history tracking

Certificate System

Automatic certificate generation

Course completion verification

Downloadable certificates

System Architecture
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
Technology Stack

Backend:

Django

Django REST Framework

Database:

PostgreSQL / SQLite (development)

Authentication:

JWT

Django Allauth (Social Login)

Payment:

Stripe API

Other Tools:

Python

Git

Docker (optional)

Project Structure
edutrack/
│
├── users/           # User and role management
├── organizations/   # Organization management
├── core/            # Institute management
├── courses/         # Course module
├── enrollments/     # Enrollment system
├── payments/        # Stripe payment integration
├── reports/         # Certificates and reports
│
├── edutrack/        # Project settings
└── manage.py
Installation Guide
1. Clone Repository
git clone https://github.com/yourusername/edutrack.git
cd edutrack
2. Create Virtual Environment
python -m venv venv

Activate environment

Windows

venv\Scripts\activate

Linux / Mac

source venv/bin/activate
3. Install Requirements
pip install -r requirements.txt
4. Apply Migrations
python manage.py makemigrations
python manage.py migrate
5. Create Superuser
python manage.py createsuperuser
6. Run Server
python manage.py runserver

Server runs at:

http://127.0.0.1:8000/
API Endpoints

Main API Root:

/api/

Available endpoints:

/user/
/organization/
/institute/
/courses/
/enrollment/
/payments/
/certificates/
Payment Flow (Stripe)
Student
   ↓
Enroll in Course
   ↓
Stripe Checkout Session
   ↓
Payment Successful
   ↓
Enrollment Activated
   ↓
Certificate Available
Roles
Role	Permissions
SuperAdmin	Manage organizations
OrgAdmin	Manage institutes and instructors
Instructor	Create and manage courses
Student	Enroll and complete courses
Security

Role-based permissions

JWT authentication

Secure Stripe payment processing

Protected API endpoints

Future Improvements

Course video lessons

Progress tracking

Assignment system

Email notifications

Certificate PDF generation

Admin analytics dashboard

Author

Developed by

Rizwan
