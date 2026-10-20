import re
import secrets
import string
from datetime import date

from .models import User


def _short_name(full_name):
    """'Sohel Rana' -> 'sohel' (first word, lowercase, letters only)"""
    first_word = full_name.strip().split()[0]
    return re.sub(r"[^a-zA-Z]", "", first_word).lower()


def generate_student_username(batch, full_name):
    start, end_suffix = batch.name.split("-")
    year_prefix = start[:2] + end_suffix

    last_seq = 0
    for u in User.objects.filter(username__startswith=year_prefix).order_by("-username"):
        number_part = u.username[len(year_prefix):len(year_prefix) + 3]
        if number_part.isdigit():
            last_seq = int(number_part)
            break

    return f"{year_prefix}{last_seq + 1:03d}{_short_name(full_name)}"


def generate_teacher_username(full_name):
    year_prefix = f"T{date.today().year}"

    last_seq = 0
    for u in User.objects.filter(username__startswith=year_prefix).order_by("-username"):
        number_part = u.username[len(year_prefix):len(year_prefix) + 3]
        if number_part.isdigit():
            last_seq = int(number_part)
            break

    return f"{year_prefix}{last_seq + 1:03d}{_short_name(full_name)}"

def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
def generate_reset_code():
    return f"{secrets.randbelow(1000000):06d}"