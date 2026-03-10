"""Launch the Eval UI web server."""

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

UI_DIR = Path(__file__).parent.parent / "ui"
DEFAULT_PORT = 3939


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Launch the Eval UI web server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
    parser.add_argument("--no-open", action="store_true", help="Don't open browser automatically")
    args = parser.parse_args()

    # Check Node.js is installed
    if not shutil.which("node"):
        print("Error: Node.js is not installed. Install it from https://nodejs.org/")
        sys.exit(1)

    npx = shutil.which("npx")
    if not npx:
        print("Error: npx not found. Ensure Node.js is properly installed.")
        sys.exit(1)

    # Install dependencies if needed
    node_modules = UI_DIR / "node_modules"
    if not node_modules.exists():
        print("Installing UI dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=UI_DIR,
            capture_output=False,
        )
        if result.returncode != 0:
            print("Error: npm install failed")
            sys.exit(1)

    # Build frontend if dist doesn't exist
    dist_dir = UI_DIR / "dist" / "client"
    if not dist_dir.exists():
        print("Building frontend...")
        result = subprocess.run(
            [npx, "vite", "build"],
            cwd=UI_DIR,
            capture_output=False,
        )
        if result.returncode != 0:
            print("Warning: Frontend build failed. Server will start without static files.")
            print("Run 'cd ui && npx vite build' to build manually, or use Vite dev server on port 5173.")

    url = f"http://localhost:{args.port}"

    if not args.no_open:
        # Open browser after a short delay (server needs time to start)
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    print(f"Starting Eval UI at {url}")
    print("Press Ctrl+C to stop\n")

    # Start the server
    env = os.environ.copy()
    env["PORT"] = str(args.port)

    try:
        subprocess.run(
            [npx, "tsx", "server/index.ts"],
            cwd=UI_DIR,
            env=env,
        )
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
