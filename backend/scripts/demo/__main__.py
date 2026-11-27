"""Demo patients (ROADMAP.md Phase 7).

    uv run python -m scripts.demo reset            # wipe and reload every demo patient
    uv run python -m scripts.demo reset harsh      # just one

Stop the API first (embedded Chroma takes one writer). The first run calls the LLM and fills
scripts/demo/cache; after that a reset is offline, free and gives identical data.
"""

import argparse
import sys
import time

from scripts.demo.generate import available, load_script
from scripts.demo.replay import replay


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(prog="python -m scripts.demo")
    parser.add_argument("command", choices=["reset"])
    parser.add_argument("patients", nargs="*", help=f"default: all ({', '.join(available())})")
    args = parser.parse_args()
    for key in args.patients or available():
        started = time.perf_counter()
        print(f"Replaying {key}...")
        pid = replay(key)
        login = load_script(key)["login"]
        print(f"  done in {time.perf_counter() - started:.0f}s: patient {pid}, "
              f"login {login['email']} / {login['password']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
