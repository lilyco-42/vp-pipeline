#!/usr/bin/env python3
"""Convert browser-exported cookie JSON to Playwright storage_state format.

Usage:
  python convert_cookies.py <input.json> <output.json>

Input: browser extension export (array of cookie objects with expirationDate)
Output: Playwright storage_state ({"cookies": [...], "origins": []})
"""
import json
import sys


def convert_same_site(val):
    """Map browser extension sameSite values to Playwright's."""
    mapping = {
        "no_restriction": "None",
        "unspecified": "Lax",
        "lax": "Lax",
        "strict": "Strict",
        None: "Lax",
    }
    return mapping.get(str(val).lower() if val else None, "Lax")


def convert_cookie(c):
    """Convert a single browser cookie to Playwright format."""
    expires = c.get("expirationDate")
    if expires is not None:
        # Playwright expects Unix timestamp in seconds (int), browser ext uses float
        if expires == -1 or expires == 0:
            expires = -1  # session cookie
        else:
            expires = int(expires)
    else:
        expires = -1

    return {
        "name": c["name"],
        "value": c["value"],
        "domain": c.get("domain", ".douyin.com"),
        "path": c.get("path", "/"),
        "expires": expires,
        "httpOnly": c.get("httpOnly", False),
        "secure": c.get("secure", False),
        "sameSite": convert_same_site(c.get("sameSite")),
    }


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.json> <output.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Input could be:
    # 1. Array of cookie objects (browser extension export)
    # 2. Already Playwright format ({"cookies": [...], "origins": [...]})
    if isinstance(raw, list):
        cookies = [convert_cookie(c) for c in raw]
    elif isinstance(raw, dict) and "cookies" in raw:
        # Already in Playwright format, just normalize
        cookies = [convert_cookie(c) for c in raw["cookies"]]
    elif isinstance(raw, dict) and "name" in raw:
        # Single cookie object
        cookies = [convert_cookie(raw)]
    else:
        print("Error: unrecognized cookie format", file=sys.stderr)
        sys.exit(1)

    # Filter: only keep douyin.com cookies (remove unrelated)
    douyin_cookies = [c for c in cookies if "douyin" in c.get("domain", "")]

    storage_state = {
        "cookies": douyin_cookies,
        "origins": [],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(storage_state, f, indent=2, ensure_ascii=False)

    print(f"Converted {len(douyin_cookies)} cookies -> {output_path}")
    # Print key cookie names for verification
    key_names = {"sessionid", "sid_guard", "ttwid", "sessionid_ss", "uid_tt", "sid_tt"}
    found = [c["name"] for c in douyin_cookies if c["name"] in key_names]
    print(f"Key cookies found: {', '.join(found) if found else 'NONE (WARNING: login may not work)'}")


if __name__ == "__main__":
    main()
