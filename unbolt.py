#!/usr/bin/env python3
import argparse
import concurrent.futures
import os
import sys
import urllib.request
import urllib.error
import uuid
from pathlib import Path


# Try to load .env from the current working directory or the script's directory
def load_env():
    env_vars = {}
    search_dirs = [Path.cwd(), Path(__file__).resolve().parent]
    for directory in search_dirs:
        env_path = directory / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        env_vars[key.strip()] = val.strip()
            break
    return env_vars


# Helper to encode multipart/form-data using standard library
def encode_multipart(filename, file_bytes, password=None, persist=True):
    boundary = f"----UnboltBoundary{uuid.uuid4().hex}"
    CRLF = b"\r\n"
    parts = []

    # File part
    parts.append(f"--{boundary}".encode("utf-8"))
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode(
            "utf-8"
        )
    )
    parts.append(b"Content-Type: application/octet-stream")
    parts.append(b"")
    parts.append(file_bytes)

    # Password part (if provided)
    if password:
        parts.append(f"--{boundary}".encode("utf-8"))
        parts.append(b'Content-Disposition: form-data; name="password"')
        parts.append(b"")
        parts.append(password.encode("utf-8"))

    # Persist part
    parts.append(f"--{boundary}".encode("utf-8"))
    parts.append(b'Content-Disposition: form-data; name="persist"')
    parts.append(b"")
    parts.append(b"true" if persist else b"false")

    # End boundary
    parts.append(f"--{boundary}--".encode("utf-8"))
    parts.append(b"")

    body = CRLF.join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def decrypt_file(file_path, server_url, password, force, persist=True):
    path = Path(file_path).resolve()
    if not path.exists():
        return file_path, False, "File does not exist"

    out_path = path.parent / f"decrypted_{path.name}"

    if out_path.exists() and not force:
        return (
            file_path,
            False,
            f"Output file '{out_path.name}' already exists. Use -f/--force to overwrite.",
        )

    try:
        with open(path, "rb") as f:
            file_bytes = f.read()
    except Exception as e:
        return file_path, False, f"Could not read input file: {e}"

    # Prepare multipart request
    try:
        body, content_type = encode_multipart(path.name, file_bytes, password, persist)
        url = f"{server_url.rstrip('/')}/decrypt"
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": content_type}
        )

        with urllib.request.urlopen(req) as response:
            decrypted_data = response.read()

            # Write out file
            with open(out_path, "wb") as out_f:
                out_f.write(decrypted_data)

            return file_path, True, f"Successfully decrypted -> {out_path.name}"
    except urllib.error.HTTPError as e:
        err_msg = e.reason
        try:
            # Try to read detail message from JSON response
            import json

            err_json = json.loads(e.read().decode("utf-8"))
            if "detail" in err_json:
                err_msg = err_json["detail"]
        except Exception:
            pass
        return file_path, False, f"API Error ({e.code}): {err_msg}"
    except urllib.error.URLError as e:
        return file_path, False, f"Connection failed to {server_url}: {e.reason}"
    except Exception as e:
        return file_path, False, f"Unexpected error: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="UNBOLT: Command Line Bulk File Decryption Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files", nargs="+", help="One or more encrypted files to decrypt"
    )
    parser.add_argument(
        "-p", "--password", help="Optional manual fallback password to try first"
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force overwrite of existing output files",
    )
    parser.add_argument(
        "-u",
        "--url",
        help="Server API URL (defaults to UNBOLT_URL in .env, or http://localhost:8000)",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not save successfully decrypted password to the server dictionary",
    )

    args = parser.parse_args()
    persist = not args.no_persist

    # Determine URL
    env_vars = load_env()
    server_url = (
        args.url
        or os.environ.get("UNBOLT_URL")
        or env_vars.get("UNBOLT_URL")
        or "http://localhost:8000"
    )

    # Pre-check conflicts
    conflicts = []
    if not args.force:
        for file_path in args.files:
            path = Path(file_path).resolve()
            if path.exists():
                out_path = path.parent / f"decrypted_{path.name}"
                if out_path.exists():
                    conflicts.append(out_path)

    if conflicts:
        print("Error: The following output files already exist:")
        for conflict in conflicts:
            print(f"  - {conflict}")
        print("Use -f / --force to overwrite these files. Aborting.")
        sys.exit(1)

    print(f"Connecting to Gateway: {server_url}")
    print(f"Processing {len(args.files)} file(s)...")

    # Run in parallel using a ThreadPoolExecutor
    results = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                decrypt_file, f, server_url, args.password, args.force, persist
            ): f
            for f in args.files
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # Print summary
    print("\nResults:")
    success_count = 0
    for file_path, success, message in results:
        status_str = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"  {status_str} | {Path(file_path).name}: {message}")
        if success:
            success_count += 1

    print(
        f"\nCompleted: {success_count}/{len(args.files)} files successfully decrypted."
    )
    if success_count < len(args.files):
        sys.exit(1)


if __name__ == "__main__":
    main()
