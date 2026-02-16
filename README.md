# Life Health CRM Backend

Production-ready backend for Life Health CRM built with FastAPI, SQLAlchemy, and Pydantic.

## Features

- **Role-Based Access Control**: Super Admin, Hospital Admin, Doctor, Nurse, Patient.
- **Authentication**: JWT Auth, Google OAuth login.
- **Database**: Async SQLAlchemy with SQLite (default) or PostgreSQL support.
- **Modules**:
  - Hospital Management
  - Doctor/Nurse/Patient Profiles
  - Medicine Inventory with logging
  - Lab Tests & Floors Management
  - Availability Scheduling

## Setup

1.  **Clone the repository** (if not already):
    ```bash
    git clone <repo-url>
    cd life_health_crm
    ```

2.  **Create virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment**:
    - Copy `.env.example` to `.env` (already done by setup script if applicable).
    - Update `GOOGLE_CLIENT_ID` and `SECRET_KEY`.

## Running the Application

Start the server with Uvicorn:

```bash
uvicorn app.main:app --reload
```

- **API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Redoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## First Run

On the first run, the system will:
1.  Create the SQLite database `sql_app.db`.
2.  Create all tables.
3.  Seed default specializations.
4.  Create a default superuser (`admin@example.com` / `adminpassword` - configurable in `.env`).

## Testing

To run tests (if implemented):
```bash
pytest
```
