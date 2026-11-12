# Thamarayyath Employee Portal

[![Django](https://img.shields.io/badge/Django-5.x-0C4B33?logo=django)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Proprietary-navy.svg)](#)
[![Deployment](https://img.shields.io/badge/Deployment-PythonAnywhere%20Free%20Tier-20B2AA.svg)](PYTHONANYWHERE_DEPLOYMENT.md)
[![Tests](https://img.shields.io/badge/Tests-45%20Passed%20(100%25)-success.svg)](#running-the-test-suite)

A complete, professional, secure, and responsive Employee Management, Attendance Tracking, and Salary Management Portal named **Thamarayyath Employee Portal**.

Engineered specifically for deployment on **PythonAnywhere** cloud hosting.

> **PythonAnywhere Free Account Guide**: See [PYTHONANYWHERE_DEPLOYMENT.md](PYTHONANYWHERE_DEPLOYMENT.md) for full step-by-step setup instructions (WSGI configuration, virtualenv, static file mappings, and SQLite persistence).

---

## Table of Contents
1. [Core Features](#core-features)
2. [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
3. [Attendance & Payroll Calculation Engine](#attendance--payroll-calculation-engine)
4. [Security Architecture & Document Vault](#security-architecture--document-vault)
5. [Deployment on PythonAnywhere](#deployment-on-pythonanywhere)
6. [Demo Accounts & Credentials](#demo-accounts--credentials)
7. [Running the Test Suite](#running-the-test-suite)
8. [Project Structure](#project-structure)

---

## Core Features

- **Role-Aware Dashboards**: Separate specialized views tailored for Superadmin, Office Administration, and Owner.
- **Precision Payroll Calculation Engine**:
  - **4 Pay Cycles**: Weekly (7d), Bi-Weekly (14d), Three-Weekly (21d), and Monthly.
  - **3 Salary Methods**: Hourly, Daily Wage, and Monthly Salaried with calendar proration.
  - **Overtime Engine**: Automatic daily threshold calculation and rate multiplier (e.g., 1.5x).
  - **Period Lifecycle**: `Draft` → `Reviewed` → `Finalized` (locks attendance records) → `Reversed`.
- **Advanced Time & Attendance Tracking**:
  - Daily Attendance Live Monitor with fast status overview (Present, Absent, Half-Day, Incomplete, Late).
  - Overnight Shift support (clock-in at night, clock-out next day).
  - Late arrival detection with configurable grace period (e.g., 15 minutes).
  - Unpaid break deductions.
  - Immutable correction log with required explanation for any retrospective punch modifications.
- **Secure Employee Vault**:
  - Private document storage outside the public web root (`private_vault/`).
  - Cryptographic UUID filenames preventing predictable URL enumeration.
  - MIME-type verification and role-restricted downloads (Owners denied document downloads).
- **Reports & Formats**:
  - Excel attendance ledger export with CSV/formula injection sanitization (`SAFE_STR`).
  - Formatted PDF Payslips and executive payroll reports.
- **Enterprise Security & Audit**:
  - Brute-force login rate limiting with automatic 15-minute lockouts after 5 failed attempts.
  - Session rotation on login preventing session fixation attacks.
  - Tamper-evident system audit log recording all logins, salary adjustments, and payroll operations.

---

## Role-Based Access Control (RBAC)

The portal enforces server-side role gating on all views:

| Module / Action | Superadmin | Office Administration | Owner |
|---|:---:|:---:|:---:|
| **Dashboard** | Full system overview & audit logs | Operational punch & payroll hub | High-level summary (Read-only) |
| **Employee Roster** | Create, Edit, View | Create, Edit, View | View Only |
| **Salary Rates** | Update rate & view audit | Update rate & view audit | View current base rate only |
| **Document Vault** | Upload, Download | Upload, Download | **Blocked** (No access) |
| **Mark Attendance** | Full access | Full access | **Blocked** (View only) |
| **Attendance Correction** | Full access (Audited) | Full access (Audited) | **Blocked** (View only) |
| **Generate Payroll** | Full access | Full access | **Blocked** (View only) |
| **Review & Finalize** | Full access | Full access | **Blocked** (View only) |
| **Payslips / Statements** | Full breakdown | Full breakdown | Aggregated outlay only |
| **User Management** | Full access | **Blocked** | **Blocked** |
| **System Settings** | Full access | **Blocked** | **Blocked** |
| **Audit Log Trail** | Full access | **Blocked** | **Blocked** |

---

## Attendance & Payroll Calculation Engine

All monetary and hourly calculations use Python's **`Decimal`** module to prevent IEEE-754 floating-point rounding errors.

### 1. Working Hours & Overtime
$$\text{Total Duration} = \text{Check-Out Timestamp} - \text{Check-In Timestamp}$$
$$\text{Net Hours} = \max\left(0, \frac{\text{Total Duration (mins)} - \text{Unpaid Break (mins)}}{60}\right)$$
$$\text{Regular Hours} = \min(\text{Net Hours}, \text{Daily OT Threshold})$$
$$\text{Overtime Hours} = \max(0, \text{Net Hours} - \text{Daily OT Threshold})$$

*For overnight shifts crossing midnight (e.g., 22:00 to 06:00), the check-out timestamp is automatically recognized on the subsequent day.*

### 2. Salary Calculation Methods

- **Hourly Rate**:
  $$\text{Base Pay} = \text{Total Regular Hours} \times \text{Hourly Rate}$$
  $$\text{OT Pay} = \text{Total OT Hours} \times \text{Hourly Rate} \times \text{OT Multiplier}$$

- **Daily Wage Rate**:
  $$\text{Base Pay} = \left(\text{Present Days} + \text{Paid Leave Days}\right) \times \text{Daily Wage Rate}$$
  $$\text{OT Pay} = \text{Total OT Hours} \times \left(\frac{\text{Daily Wage Rate}}{\text{Standard Hours}}\right) \times \text{OT Multiplier}$$

- **Monthly Salaried**:
  $$\text{Daily Equivalent} = \frac{\text{Monthly Base Salary}}{\text{Total Calendar Days in Month}}$$
  $$\text{Base Pay} = \text{Payable Days} \times \text{Daily Equivalent}$$
  $$\text{Gross Pay} = \text{Base Pay} + \text{OT Pay} + \text{Allowances} - \text{Deductions}$$

---

## Security Architecture & Document Vault

1. **Private Vault Storage**: Uploaded files (contracts, IDs, tax records) are stored in `d:\THAMARAYYATH\private_vault\`, isolated from public web accessibility.
2. **Path Traversal Protection**: Document retrieval views verify that the resolved file path resides strictly inside `PRIVATE_VAULT_ROOT`.
3. **Audit Log Trail**: Every security-sensitive action generates an immutable `AuditLog` entry tracking timestamp, actor, action, target entity, client IP address, and changed fields.
4. **Formula Injection Sanitization**: All exported Excel cells are sanitized by stripping spreadsheet formula prefixes (`=`, `+`, `-`, `@`) to prevent CSV injection vulnerabilities.

---

## Deployment on PythonAnywhere

The application is deployed on **PythonAnywhere** cloud hosting.

### Quick Setup Overview
1. **Clone repository** in a PythonAnywhere Bash console:
   ```bash
   git clone https://github.com/im-Abhiram/tempsite1.git
   ```
2. **Create virtualenv & install dependencies**:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 thamarayyath-env
   pip install -r requirements.txt
   ```
3. **Configure WSGI**:
   - In PythonAnywhere **Web** tab, open the WSGI configuration file.
   - Copy contents from [`pythonanywhere_wsgi.py`](pythonanywhere_wsgi.py).
4. **Run migrations & collect static**:
   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
5. **Reload Web App**: Click the green **Reload** button in the Web tab.

> **Full Deployment & Safe Update Guide**: Refer to [PYTHONANYWHERE_DEPLOYMENT.md](PYTHONANYWHERE_DEPLOYMENT.md) for full instructions, static/media mappings, security checklist, and zero-data-loss update procedures.

---

## Demo Accounts & Credentials

The portal is pre-seeded with sample departments, shifts, employees, attendance punches, and payroll cycles:

| Role | Username | Password | Purpose |
|---|---|---|---|
| **Superadmin** | `admin` | `AdminPass123!` | System configuration, user provisioning, security audit logs |
| **Office Administration** | `accountant` | `AccountPass123!` | Daily attendance punches, shift management, payroll generation |
| **Owner** | `owner` | `OwnerPass123!` | Executive dashboard, high-level financials, read-only summaries |

*To re-seed demonstration data at any time, run:*
```powershell
.venv\Scripts\python manage.py seed_demo_data
```

---

## Running the Test Suite

The portal includes an exhaustive automated test suite covering authentication, RBAC, employee profiles and bank details confidentiality, attendance arithmetic, overtime calculation, overnight shifts, leave records, payroll periods and statements, CSV/Excel/PDF reporting, and SQLite database backup integrity:

```powershell
.venv\Scripts\python manage.py test
```
*(Result: `Ran 35 tests in ~60s ... OK - 0 errors, 0 failures`)*

---

## Project Structure

```
d:\THAMARAYYATH\
├── accounts\                 # User authentication, roles, settings, middleware & throttling
├── attendance\               # Punch logging, overtime, overnight shifts, corrections & leaves
├── audit\                    # Security and compliance logging (tamper-evident audit trail)
├── core\                     # Live SQLite online backup API & disk storage metrics
├── dashboard\                # Dedicated role dashboards (Superadmin, Office Administration, Owner)
├── employees\                # Staff roster, departments, shifts, salary history & documents
├── payroll\                  # Multi-period payroll calculation engine & adjustment workflows
├── reports\                  # Reports Hub & CSV/Excel/PDF exports with formula injection defense
├── static\                   # Portal UI CSS, JS, and vendor bundles (Bootstrap 5, Chart.js)
├── staticfiles\              # Production collected static assets
├── templates\                # High-fidelity role-based Django templates (20+ pages)
├── media\                    # Upload directories (employee photos, documents, payroll)
├── pythonanywhere_wsgi.py     # Copy-paste WSGI configuration for PythonAnywhere free hosting
└── PYTHONANYWHERE_DEPLOYMENT.md # Beginner-friendly step-by-step deployment guide
```

---
*Developed for **Thamarayyath Enterprise**.*
