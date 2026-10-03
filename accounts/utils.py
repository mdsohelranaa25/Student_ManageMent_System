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
    """
    Batch '2023-24', name 'Sohel Rana' -> '2024001sohel', '2024002sohel', ...
    """
    start, end_suffix = batch.name.split("-")
    year_prefix = start[:2] + end_suffix  # '20' + '24' = '2024'

    last_user = (
        User.objects.filter(username__startswith=year_prefix)
        .order_by("-username")
        .first()
    )
    if last_user:
        last_seq = int(last_user.username[len(year_prefix):len(year_prefix) + 3])
        seq = last_seq + 1
    else:
        seq = 1

    return f"{year_prefix}{seq:03d}{_short_name(full_name)}"


def generate_teacher_username(full_name):
    """
    'T' + current year + sequence + name -> 'T2026001sohel', ...
    """
    year_prefix = f"T{date.today().year}"

    last_user = (
        User.objects.filter(username__startswith=year_prefix)
        .order_by("-username")
        .first()
    )
    if last_user:
        last_seq = int(last_user.username[len(year_prefix):len(year_prefix) + 3])
        seq = last_seq + 1
    else:
        seq = 1

    return f"{year_prefix}{seq:03d}{_short_name(full_name)}"


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))