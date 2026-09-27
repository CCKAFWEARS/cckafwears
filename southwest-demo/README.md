# Softwareized

Fictional airline-booking training site inspired by common airline booking patterns.

Safety: no real payment credentials are collected or processed. The payment step accepts only a fictional test-card fields.

Deploy on Render with root directory `southwest-demo`, build `pip install -r requirements.txt`, and start `gunicorn app:app`. Set `MONITOR_PASSWORD` in Render.
