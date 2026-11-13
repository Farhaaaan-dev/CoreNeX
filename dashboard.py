"""
CoreNex Dashboard Launcher
===========================
Starts a local HTTP server so the browser can fetch the CSV data files,
then opens the dashboard in your default browser.

Usage
-----
    python dashboard.py

Stop
----
    Press Enter  or  Ctrl+C
"""
import http.server
import socketserver
import webbrowser
import threading
import os
import sys

PORT      = 8080
HOST      = "localhost"
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

REQUIRED_FILES = [
    "index.html",
    "model_evaluation.csv",
    "model_comparison.csv",
    "best_model_per_skill.csv",
    "future_forecast.csv",
    "forecasting_summary.csv",
]


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serve files from the CoreNex project directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, fmt, *args):   # silence per-request logs
        pass


def _run_server(httpd: socketserver.TCPServer) -> None:
    httpd.serve_forever()


def _check_files() -> bool:
    missing = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(DIRECTORY, f))]
    if missing:
        print("\n  ⚠  Missing required files:")
        for f in missing:
            print(f"       {f}")
        return False
    return True


def main() -> None:
    print("=" * 54)
    print("   CoreNex — Labour Market Intelligence")
    print("=" * 54)

    if not _check_files():
        print("\n  Run forecast_engine.py first to generate the data files.")
        sys.exit(1)

    print(f"\n  Serving : {DIRECTORY}")
    print(f"  URL     : http://{HOST}:{PORT}")
    print(f"  Skills  : 236 eligible skills loaded from CSV files")
    print(f"\n  Opening your browser...")
    print(f"  Press Enter (or Ctrl+C) to stop the server.\n")

    try:
        httpd = socketserver.TCPServer((HOST, PORT), _Handler)
    except OSError as exc:
        # Port already in use — try to open browser anyway
        if getattr(exc, "errno", None) in (98, 48, 10048) or \
                "address already in use" in str(exc).lower():
            print(f"  Port {PORT} is already in use.")
            print(f"  Attempting to open browser at http://{HOST}:{PORT} ...\n")
            webbrowser.open(f"http://{HOST}:{PORT}")
            try:
                input("  Press Enter to exit.\n")
            except KeyboardInterrupt:
                pass
            return
        raise

    thread = threading.Thread(target=_run_server, args=(httpd,), daemon=True)
    thread.start()

    webbrowser.open(f"http://{HOST}:{PORT}")

    try:
        input()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        print("\n  CoreNex stopped. Goodbye.\n")


if __name__ == "__main__":
    main()
