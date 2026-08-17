"""Write the API's OpenAPI document to a file.

Deliberately does not start a server. The schema is derived from the route
annotations at import time, so `make contracts` works in CI, in a container
build and on a laptop with nothing running — the alternative is booting the app,
polling `/openapi.json` and shutting it down, which fails for exactly the reasons
you least want in a codegen step.

Keys are sorted and the file ends in a newline so that regenerating an unchanged
API produces a byte-identical file. A generated artefact that reorders itself on
every run cannot be diffed, and a contract you cannot diff is a contract nobody
reviews.
"""

import json
import pathlib
import sys

from hotelagent.main import app


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: export_openapi.py <destination.json>", file=sys.stderr)
        return 2

    destination = pathlib.Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")

    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
