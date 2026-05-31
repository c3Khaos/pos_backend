# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron         import CronTrigger
import pytz

from services.report_service import get_daily_report_data, get_recipient_emails
from services.email_service  import send_daily_report

EAT = pytz.timezone("Africa/Nairobi")


def run_daily_report():
    """Pulls all user emails from DB, compiles report, sends to everyone."""
    print("[scheduler] Running daily report job...")
    try:
        recipients = get_recipient_emails()
        print(f"[scheduler] Found {len(recipients)} recipient(s)")

        if not recipients:
            print("[scheduler] No users with emails found — skipping.")
            return

        data   = get_daily_report_data()
        result = send_daily_report(data, recipients)
        print(f"[scheduler] Report job complete: {result}")

    except Exception as e:
        print(f"[scheduler] Daily report job failed: {e}")


def init_scheduler(app):
    """
    Call this inside your Flask app factory, AFTER db.init_app(app).

    Example in create_app():
        from scheduler import init_scheduler
        init_scheduler(app)
    """
    scheduler = BackgroundScheduler(timezone=EAT)

    # Fires every day at 22:00 EAT (10 PM Nairobi time)
    scheduler.add_job(
        func             = lambda: _run_with_context(app),
        trigger          = CronTrigger(hour=22, minute=0, timezone=EAT),
        id               = "daily_report",
        name             = "Send Daily Report",
        replace_existing = True,
    )

    scheduler.start()
    print("[scheduler] Daily report scheduled for 22:00 EAT")
    return scheduler


def _run_with_context(app):
    """
    APScheduler runs outside Flask's request context.
    Pushes an app context so db.session works inside the job.
    """
    with app.app_context():
        run_daily_report()