"""Command line: python -m golf_demo [serve|followups]

`serve` (the default) starts the demo at http://localhost:8000.
`followups` sends any follow-ups that are due and exits, so a scheduler
(cron) can run it every hour once this is live for a real course.
"""

import argparse

from .leads import LeadStore
from .notify import Sender
from .server import run_due_follow_ups, serve

DATA = "golf_demo_data/leads.json"


def main():
    p = argparse.ArgumentParser(prog="python -m golf_demo")
    p.add_argument("command", nargs="?", default="serve", choices=["serve", "followups"])
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1",
                   help="use 0.0.0.0 to let other devices on your network open it")
    p.add_argument("--data", default=DATA, help="where leads are saved")
    args = p.parse_args()

    store, sender = LeadStore(args.data), Sender()
    if args.command == "followups":
        print(f"Sent {run_due_follow_ups(store, sender)} follow-ups.")
        return

    httpd = serve(store, sender, args.host, args.port)
    print(f"Inquiry form:     http://localhost:{args.port}/")
    print(f"Staff dashboard:  http://localhost:{args.port}/dashboard")
    print(f"Email: {'connected' if sender.can_email else 'demo mode'}   "
          f"Texts: {'connected' if sender.can_text else 'demo mode'}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
