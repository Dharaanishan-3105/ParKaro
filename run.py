import os
import threading
import time
import webbrowser

from django.core.management import execute_from_command_line


def open_browser():
    """Open the default browser after the server starts."""
    # Small delay to give runserver time to start
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000/")


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "parkaro_backend.settings")

    # Start browser opener thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Start Django development server
    execute_from_command_line(["manage.py", "runserver"])


if __name__ == "__main__":
    main()

