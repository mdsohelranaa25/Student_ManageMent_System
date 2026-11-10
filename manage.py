#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    # Auto-detect project venv and re-execute if run with system python
    base_dir = Path(__file__).resolve().parent
    venv_py = base_dir / "venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        try:
            current_py = Path(sys.executable).resolve()
            target_py = venv_py.resolve()
            if current_py != target_py:
                import subprocess
                sys.exit(subprocess.call([str(target_py)] + sys.argv))
        except Exception:
            pass

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
