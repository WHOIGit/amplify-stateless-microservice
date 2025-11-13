"""Helper script for exercising the base64 grayscale service."""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send an image to the grayscale service and save the response."
    )
    parser.add_argument(
        "input_image",
        type=Path,
        help="Path to the image to convert.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("grayscale.png"),
        help="Where to write the grayscale PNG (default: %(default)s).",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8020/image/grayscale",
        help="Endpoint URL or base (host:port) for the running service.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    parsed = urllib.parse.urlparse(args.url)
    if parsed.path in ("", "/"):
        parsed = parsed._replace(path="/image/grayscale")
    endpoint = urllib.parse.urlunparse(parsed)

    image_bytes = args.input_image.read_bytes()
    payload = json.dumps({
        "image_b64": base64.b64encode(image_bytes).decode("ascii"),
    }).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        sys.stderr.write(f"Request failed ({exc.code}): {exc.read().decode('utf-8')}\n")
        return 1

    data = json.loads(body)
    grayscale = base64.b64decode(data["grayscale_b64"])
    args.output.write_bytes(grayscale)
    print(f"Saved grayscale image to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
