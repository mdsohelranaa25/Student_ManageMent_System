import csv
import io
import re
import secrets
import string
from datetime import date

from django.core.mail import send_mail
from academics.models import Batch
from .models import User


def _short_name(full_name):
    """'Sohel Rana' -> 'sohel' (first word, lowercase, letters only)"""
    if not full_name:
        return "student"
    first_word = full_name.strip().split()[0]
    cleaned = re.sub(r"[^a-zA-Z]", "", first_word).lower()
    return cleaned or "student"


def generate_student_username(batch, full_name):
    """
    Fallback username generator if registration number is not explicitly supplied.
    e.g. batch '2023-24' -> prefix '2024' -> '2024001sohel'
    """
    if batch and "-" in batch.name:
        parts = batch.name.split("-")
        year_prefix = parts[0][:2] + parts[1]
    elif batch and batch.name:
        digits = re.sub(r"[^0-9]", "", batch.name)
        year_prefix = digits[:4] if len(digits) >= 4 else f"{date.today().year % 100:02d}00"
    else:
        year_prefix = f"{date.today().year % 100:02d}00"

    last_seq = 0
    for u in User.objects.filter(username__startswith=year_prefix).order_by("-username"):
        number_part = u.username[len(year_prefix):len(year_prefix) + 3]
        if number_part.isdigit():
            last_seq = int(number_part)
            break

    short = _short_name(full_name)
    seq = last_seq + 1
    username = f"{year_prefix}{seq:03d}{short}"

    while User.objects.filter(username=username).exists():
        seq += 1
        username = f"{year_prefix}{seq:03d}{short}"

    return username


def generate_teacher_username(full_name):
    year_prefix = f"T{date.today().year}"

    last_seq = 0
    for u in User.objects.filter(username__startswith=year_prefix).order_by("-username"):
        number_part = u.username[len(year_prefix):len(year_prefix) + 3]
        if number_part.isdigit():
            last_seq = int(number_part)
            break

    short = _short_name(full_name)
    seq = last_seq + 1
    username = f"{year_prefix}{seq:03d}{short}"
    while User.objects.filter(username=username).exists():
        seq += 1
        username = f"{year_prefix}{seq:03d}{short}"

    return username


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_reset_code():
    return f"{secrets.randbelow(1000000):06d}"


def _normalize_header(h):
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def parse_student_rows_from_file(uploaded_file):
    """
    Parses rows from either an .xlsx or a .csv uploaded file.
    Returns list of dicts with keys: name, email, phone, batch, roll, reg
    """
    filename = uploaded_file.name.lower()
    raw_rows = []

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        import openpyxl
        wb = openpyxl.load_workbook(uploaded_file, data_only=True)
        sheet = wb.active
        headers = None
        for row in sheet.iter_rows(values_only=True):
            if not row or all(v is None or str(v).strip() == "" for v in row):
                continue
            if headers is None:
                headers = [_normalize_header(c) for c in row]
                continue
            row_dict = {}
            for h, val in zip(headers, row):
                row_dict[h] = "" if val is None else str(val).strip()
            raw_rows.append(row_dict)
    else:
        # CSV parsing (handles UTF-8, UTF-8 BOM, and Latin-1)
        content = uploaded_file.read()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        reader = csv.reader(io.StringIO(text))
        headers = None
        for row in reader:
            if not row or all(str(v).strip() == "" for v in row):
                continue
            if headers is None:
                headers = [_normalize_header(c) for c in row]
                continue
            row_dict = {}
            for h, val in zip(headers, row):
                row_dict[h] = str(val).strip()
            raw_rows.append(row_dict)

    # Standardize column mapping for: Name, Email, Phone, Batch, Roll, Reg
    standardized = []
    for r in raw_rows:
        std = {
            "name": "",
            "email": "",
            "phone": "",
            "batch": "",
            "roll": "",
            "reg": "",
        }
        for k, v in r.items():
            if k in ("name", "studentname", "fullname"):
                std["name"] = v
            elif k in ("email", "emailaddress", "mail"):
                std["email"] = v
            elif k in ("phone", "mobile", "phonenumber", "contact"):
                std["phone"] = v
            elif k in ("batch", "session", "admissionyear"):
                std["batch"] = v
            elif k in ("roll", "rollno", "rollnumber"):
                std["roll"] = v
            elif k in ("reg", "regno", "registration", "registrationno", "registrationnumber", "studentid", "regnumber"):
                std["reg"] = v
        standardized.append(std)

    return standardized


def import_students_from_file(uploaded_file, request=None):
    """
    Reads student rows from Excel/CSV.
    Uses the Registration Number (Reg) directly as the unique Username / Login ID.
    Generates a secure password, saves user in database, and emails credentials.
    """
    rows = parse_student_rows_from_file(uploaded_file)

    created_students = []
    errors = []

    domain = "localhost:8000"
    if request:
        domain = request.get_host()

    for idx, r in enumerate(rows, start=2): # line 1 was headers
        name = r.get("name", "").strip()
        email = r.get("email", "").strip().lower()
        phone = r.get("phone", "").strip()
        batch_name = r.get("batch", "").strip()
        roll_raw = r.get("roll", "").strip()
        reg = r.get("reg", "").strip()

        if not name or not email:
            errors.append({
                "row": idx,
                "name": name or "(empty)",
                "email": email or "(empty)",
                "reg": reg or "(empty)",
                "error": "Name and Email are required.",
            })
            continue

        if not reg:
            errors.append({
                "row": idx,
                "name": name,
                "email": email,
                "reg": "(empty)",
                "error": "Registration Number (Reg) is required as it serves as the student's Login ID.",
            })
            continue

        # Registration Number acts directly as the student's unique Login ID (Username)
        username = reg

        if User.objects.filter(username=username).exists():
            errors.append({
                "row": idx,
                "name": name,
                "email": email,
                "reg": reg,
                "error": f"A student with Registration No / Login ID '{username}' already exists in the database.",
            })
            continue

        if User.objects.filter(email=email).exists():
            errors.append({
                "row": idx,
                "name": name,
                "email": email,
                "reg": reg,
                "error": f"An account already exists with email '{email}'.",
            })
            continue

        # Batch resolution
        batch = None
        if batch_name:
            batch, _ = Batch.objects.get_or_create(
                name=batch_name,
                defaults={"is_running": True}
            )

        # Roll resolution
        roll = None
        if roll_raw:
            digits = re.sub(r"[^0-9]", "", roll_raw)
            if digits:
                roll = int(digits)

        # Generate secure random password
        password = generate_password(10)

        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role="student",
                phone=phone,
                batch=batch,
                roll=roll,
                registration_no=reg,
                first_name=name,
            )

            # Send Email
            email_sent = False
            email_error = None
            try:
                protocol = "https" if (request and request.is_secure()) else "http"
                login_url = f"{protocol}://{domain}/accounts/login/"

                subject = "Welcome to IIT JU Student Portal - Your Account Credentials"
                message = (
                    f"Dear {name},\n\n"
                    f"Your student account has been successfully created on the IIT Jahangirnagar University Portal.\n\n"
                    f"Your Official Login Credentials:\n"
                    f"-----------------------------------------\n"
                    f"Portal URL       : {login_url}\n"
                    f"Registration No  : {reg}\n"
                    f"Login ID         : {username}  (Use your Registration No to log in)\n"
                    f"Password         : {password}\n"
                    f"Batch            : {batch.name if batch else 'N/A'}\n"
                    f"Class Roll No    : {roll if roll is not None else 'N/A'}\n"
                    f"-----------------------------------------\n\n"
                    f"Please log in to your dashboard to view class schedules, attendance, results, and notices.\n"
                    f"You may change your password anytime from your dashboard.\n\n"
                    f"Important Notice: Your Registration Number, Roll, and Batch are officially locked.\n\n"
                    f"Warm regards,\n"
                    f"Institute of Information Technology (IIT)\n"
                    f"Jahangirnagar University, Savar, Dhaka-1342"
                )
                send_mail(subject, message, None, [email], fail_silently=False)
                email_sent = True
            except Exception as mail_err:
                email_error = str(mail_err)

            created_students.append({
                "row": idx,
                "name": name,
                "username": username,
                "password": password,
                "email": email,
                "batch": batch.name if batch else "-",
                "roll": roll if roll is not None else "-",
                "reg": reg,
                "email_sent": email_sent,
                "email_error": email_error,
            })

        except Exception as e:
            errors.append({
                "row": idx,
                "name": name,
                "email": email,
                "reg": reg,
                "error": f"Failed to create user: {str(e)}",
            })

    return {
        "total_rows": len(rows),
        "success_count": len(created_students),
        "error_count": len(errors),
        "created_students": created_students,
        "errors": errors,
    }
