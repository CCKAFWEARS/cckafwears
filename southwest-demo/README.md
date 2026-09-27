# Southwest Training Demo

Fictional airline-booking training site inspired by common airline booking patterns.

Safety: no full card numbers, CVV, passwords, PINs or one-time verification codes are collected. The payment step accepts only a demo method and fictional last four digits.

Deploy on Render with root directory `southwest-demo`, build `pip install -r requirements.txt`, and start `gunicorn app:app`. Set `MONITOR_PASSWORD` in Render.
