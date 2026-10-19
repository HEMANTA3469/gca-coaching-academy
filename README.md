# GCA Coaching Academy Portal

A responsive Flask + SQLite starter portal for GCA Coaching Academy. Includes public student admission, student photo upload, generated student ID and admission confirmation PDFs, class-wise learning resources, online-class links, video/document uploads, exam schedules, gallery, fee payment records, attendance, MCQ practice/results, admin settings, and optional Google Sheets admission sync.

## Features
- Public admission form with student/father/mother details, date of birth, class/course, contact and passport-style photo.
- Auto-generated GCA student ID.
- Successful admission page with downloadable ID-card PDF and admission details PDF.
- Admin login and dashboard; manage students, classes, notes, videos, online class links, exams, payments, attendance, question-bank files and individual MCQs, gallery, logo, colors, homepage copy, contact/footer and admin password.
- Public class-wise learning library, online class page, exam schedule, gallery and MCQ practice.
- `/sitemap.xml` and `/robots.txt` endpoints for search engine discovery.
- Optional Google Sheets sync when an admission is submitted.

## Local setup (Windows PowerShell)
1. Extract the ZIP.
2. Open the extracted folder in VS Code.
3. Run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = "replace-with-a-long-random-secret"
$env:ADMIN_PASSWORD = "replace-with-a-strong-initial-password"
python app.py
```

4. Visit `http://127.0.0.1:5000`.
5. Admin login: `/admin/login`. The initial password is the value of `ADMIN_PASSWORD` when the database is created; if not set, it is `GcaAdmin@123`. Change it from Admin → Website Settings immediately. If the database already exists, changing `ADMIN_PASSWORD` alone does not reset the stored password hash.

## Render deployment
- Push the extracted source files to a private GitHub repository (not the ZIP alone).
- Create a Render Web Service connected to that repository.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Set `SECRET_KEY` and `ADMIN_PASSWORD` as private environment variables. Do not commit secrets.
- Important: Render Free Web Services do not provide persistent local disk. The SQLite database and uploaded files can be lost on redeploy/restart. For real use, attach a paid Persistent Disk mounted at `/var/data`, and set `DATABASE_PATH=/var/data/gca_academy.db` and `UPLOAD_DIR=/var/data/uploads`. Ensure the upload folders are writable. Alternatively migrate the database to a managed persistent database and files to object storage. Back up the database and uploads regularly.
- Video files can be large. Prefer YouTube unlisted, Google Drive with suitable permissions, or another hosted video platform and paste the URL into the resource form instead of storing large videos on the app server.

## Optional Google Sheets integration
Admission records are stored in SQLite first. Google Sheets sync is attempted only if both `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_SHEET_ID` are configured.

1. In Google Cloud Console, create/select a project and enable the Google Sheets API (and Drive API if needed).
2. Create a service account and a JSON key. Treat the key as a password; never upload it to GitHub.
3. Create a Google Sheet and share it with the service-account email as an Editor.
4. Copy the spreadsheet ID from its URL into `GOOGLE_SHEET_ID`.
5. Put the full service-account JSON contents into the private `GOOGLE_SERVICE_ACCOUNT_JSON` environment variable on Render. For local testing, set the same variable in your shell, not in source code.
6. Install dependencies from `requirements.txt`. The first worksheet receives one row per successful admission with columns: student code, name, father, mother, DOB, gender, phone, email, address, class, course and admission date. Create a header row yourself before the first submission.
7. Check Render logs for `Google Sheets sync failed` if a row does not appear. SQLite remains the primary data store; sync failures do not roll back admission.

## Important limitations / production checklist
- This is an extensible starter portal, not a complete ERP. It does not include student accounts, online payment gateway reconciliation, automatic class streaming, SMS/WhatsApp alerts, bulk CSV import, fee receipts, exam marksheets or parental access yet.
- The online class feature publishes meeting URLs or hosted video links; it does not itself stream live video.
- Admin forms should be protected with CSRF tokens before exposing the site publicly. Use HTTPS, a strong admin password, regular backups, upload-size limits, and least-privilege access.
- Review consent and privacy practices before collecting minors' data/photos. Limit access to student information and avoid public sharing of private student PDFs.
- ID card and admission PDFs require ReportLab, installed through `requirements.txt`.

## Routes
- `/` public home
- `/admission` admission form
- `/learning` class-wise notes/resources
- `/online-classes` live class links/videos
- `/exams` exam schedule
- `/gallery` gallery
- `/mcq` MCQ test
- `/admin/login` admin login
- `/admin` admin dashboard
- `/admin/settings` branding and site editor
- `/sitemap.xml` sitemap
