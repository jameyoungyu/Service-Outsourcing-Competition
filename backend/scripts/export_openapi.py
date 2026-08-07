"""Export the generated FastAPI schema used as the frozen frontend contract."""

import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "openapi.json"
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
