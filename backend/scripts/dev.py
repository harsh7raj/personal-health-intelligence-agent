"""One-command local dev runner (cross-platform, standard library only).

    cd backend
    uv run python -m scripts.dev            # Postgres -> migrate -> seed if empty -> API + web
    uv run python -m scripts.dev --reload   # restart the API on code changes
    uv run python -m scripts.dev --stop-db  # stop the portable Postgres (LOCAL_PG_HOME)

Postgres: uses whatever already listens at DATABASE_URL; otherwise starts the portable
install at LOCAL_PG_HOME (Windows without Docker or admin rights, see README); otherwise
runs `docker compose up -d`. Ctrl+C stops the API and the web server; Postgres keeps running.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, make_url, text

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
API_PORT = 8001
WEB_PORT = 5173
DEMO_EMAIL = "demo@phia.health"
IS_WINDOWS = os.name == "nt"


def _pg_addr() -> tuple[str, int]:
    url = make_url(get_settings().DATABASE_URL)
    return url.host or "localhost", url.port or 5432


def _pg_up() -> bool:
    try:
        with socket.create_connection(_pg_addr(), timeout=1.0):
            return True
    except OSError:
        return False


def _wait_for_pg(seconds: int = 60) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _pg_up():
            return True
        time.sleep(1)
    return False


def _pg_ctl(action: str) -> int:
    home = Path(get_settings().LOCAL_PG_HOME)
    exe = home / "pgsql" / "bin" / ("pg_ctl.exe" if IS_WINDOWS else "pg_ctl")
    args = [str(exe), "-D", str(home / "data"), "-w"]
    if action == "start":
        _, port = _pg_addr()
        args += ["-l", str(home / "postgres.log"), "-o", f"-p {port} -c listen_addresses=localhost"]
    # No pipes (the server would inherit them), and its own process group on Windows so
    # Ctrl+C in this terminal doesn't stop the database along with the dev servers.
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    return subprocess.call(
        [*args, action],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def ensure_postgres() -> None:
    host, port = _pg_addr()
    if _pg_up():
        print(f"Postgres: already running on {host}:{port}")
        return
    if get_settings().LOCAL_PG_HOME:
        print(f"Postgres: starting portable install at {get_settings().LOCAL_PG_HOME}")
        _pg_ctl("start")
    elif shutil.which("docker"):
        print("Postgres: docker compose up -d")
        subprocess.check_call(["docker", "compose", "up", "-d"], cwd=BACKEND)
    else:
        sys.exit(
            "Postgres isn't running, and neither LOCAL_PG_HOME nor docker is available. "
            "See README > Run it locally."
        )
    if not _wait_for_pg():
        sys.exit(f"Postgres did not come up on {host}:{port}.")


def ensure_database() -> None:
    """Create the app database if missing (docker compose does this; a fresh portable
    install only has the 'postgres' maintenance database)."""
    url = make_url(get_settings().DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("select 1 from pg_database where datname = :db"), {"db": url.database}
            ).first()
            if not exists:
                print(f"Postgres: creating database {url.database}")
                conn.execute(text(f'create database "{url.database}"'))
    finally:
        admin.dispose()


def _user_exists(email: str) -> bool:
    engine = create_engine(get_settings().DATABASE_URL)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("select 1 from users where email = :email"), {"email": email}
            ).first()
            return row is not None
    finally:
        engine.dispose()


def _missing_story_patients() -> list[str]:
    """Story-script demo patients (scripts/demo/patients) not loaded yet."""
    from scripts.demo.generate import available, load_script

    return [k for k in available() if not _user_exists(load_script(k)["login"]["email"])]


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:  # terminate() would leave node/uvicorn children behind
        subprocess.call(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # progress lines appear before child output
    parser = argparse.ArgumentParser(description="Run the app locally.")
    parser.add_argument("--reload", action="store_true", help="restart the API on code changes")
    parser.add_argument("--no-web", action="store_true", help="start only the API")
    parser.add_argument("--stop-db", action="store_true", help="stop the portable Postgres")
    args = parser.parse_args()

    if args.stop_db:
        if not get_settings().LOCAL_PG_HOME:
            sys.exit("LOCAL_PG_HOME is not set; with Docker use `docker compose stop`.")
        sys.exit(_pg_ctl("stop"))

    ensure_postgres()
    ensure_database()
    print("Migrations: alembic upgrade head")
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND)
    # Seed before the API starts: the embedded Chroma store takes one writer at a time.
    if not _user_exists(DEMO_EMAIL):
        print("Seeding the demo patient")
        subprocess.check_call([sys.executable, "-m", "scripts.seed_demo"], cwd=BACKEND)
    missing = _missing_story_patients()
    if missing:  # replayed from the committed LLM cache: offline and free
        print(f"Loading demo patients: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "scripts.demo", "reset", *missing], cwd=BACKEND)

    procs: list[subprocess.Popen] = []
    api_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT)]
    procs.append(subprocess.Popen(api_cmd + (["--reload"] if args.reload else []), cwd=BACKEND))

    if not args.no_web:
        node = shutil.which("node")
        npm = shutil.which("npm")
        if not node or not npm:
            sys.exit("Node.js (node and npm) is needed for the web app.")
        if not (FRONTEND / "node_modules").exists():
            subprocess.check_call([npm, "ci"], cwd=FRONTEND)
        vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"  # = `npm run dev`
        procs.append(subprocess.Popen([node, str(vite), "--port", str(WEB_PORT)], cwd=FRONTEND))

    print(f"\nAPI  http://localhost:{API_PORT}/api/health")
    if not args.no_web:
        print(f"Web  http://localhost:{WEB_PORT}   (demo login: {DEMO_EMAIL} / demo-pass-123)")
    print("Ctrl+C to stop (Postgres keeps running).\n")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            _stop(p)


if __name__ == "__main__":
    main()
