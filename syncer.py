#!/usr/bin/env python3
import os
import shutil
import argparse
from pathlib import Path
import requests
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
import uvicorn
import threading
import json

# --------------------------
# Ignore handling
# --------------------------


def load_files_to_ignore(ignore_file):
    patterns = []
    if ignore_file.exists():
        with open(ignore_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    return patterns


def should_ignore(rel_path, ignore_patterns):
    for pat in ignore_patterns:
        if Path(rel_path).match(pat):
            return True
    return False

# --------------------------
# Local file listing
# --------------------------


def get_file_list(folder, ignore_patterns):
    folder = Path(folder).resolve()
    file_list = {}
    for root, _, files in os.walk(folder):
        rel_root = Path(root).relative_to(folder)
        for file in files:
            rel_path = rel_root / file
            if should_ignore(rel_path, ignore_patterns):
                continue
            fpath = folder / rel_path
            stat = fpath.stat()
            file_list[str(rel_path)] = {
                "size": stat.st_size,
                "mtime": int(stat.st_mtime)
            }
    return file_list

# --------------------------
# Server (FastAPI)
# --------------------------


def start_server(folder, port):
    app = FastAPI()
    folder = Path(folder).resolve()
    ignore_patterns = load_files_to_ignore(folder / ".syncignore")

    @app.get("/list")
    def list_files():
        return get_file_list(folder, ignore_patterns)

    @app.get("/get/{file_path:path}")
    def get_file(file_path: str):
        f = folder / file_path
        if f.exists():
            return FileResponse(f)
        return {"error": "file not found"}

    @app.post("/put/{file_path:path}")
    async def put_file(file_path: str, file: UploadFile = File(...)):
        fpath = folder / file_path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        with open(fpath, "wb") as out_f:
            out_f.write(await file.read())
        return {"status": "ok"}

    uvicorn.run(app, host="0.0.0.0", port=port)


# --------------------------
# Client sync logic
# --------------------------
def sync_with_peer(folder, peer_url, ignore_patterns, dry_run=False,
                   log=False):
    folder = Path(folder).resolve()
    local_files = get_file_list(folder, ignore_patterns)

    try:
        r = requests.get(f"{peer_url}/list", timeout=10)
        peer_files = r.json()
    except Exception as e:
        print(f"[ERROR] Cannot connect to peer {peer_url}: {e}")
        return

    all_paths = set(local_files.keys()).union(set(peer_files.keys()))

    for path in all_paths:
        if should_ignore(path, ignore_patterns):
            continue

        local_meta = local_files.get(path)
        peer_meta = peer_files.get(path)

        action = determine_action(local_meta, peer_meta)
        if not action:
            continue

        local_path = folder / path

        if action in ("download", "download_new"):
            if log or dry_run:
                print(f"[{action.upper()}] {path}")
            if not dry_run:
                download_file(peer_url, path, local_path)

        elif action in ("upload", "upload_new"):
            if log or dry_run:
                print(f"[{action.upper()}] {path}")
            if not dry_run:
                upload_file(peer_url, path, local_path)


def determine_action(local_meta, peer_meta):
    """
    Returns one of:
    'upload', 'upload_new', 'download', 'download_new', or None (skip)
    """
    if local_meta and peer_meta:
        if peer_meta["mtime"] > local_meta["mtime"]:
            return "download"
        elif local_meta["mtime"] > peer_meta["mtime"]:
            return "upload"
        else:
            return None
    elif local_meta and not peer_meta:
        return "upload_new"
    elif peer_meta and not local_meta:
        return "download_new"
    else:
        return None


def download_file(peer_url, path, local_path):
    url = f"{peer_url}/get/{path}"
    r = requests.get(url)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(r.content)


def upload_file(peer_url, path, local_path):
    url = f"{peer_url}/put/{path}"
    with open(local_path, "rb") as f:
        files = {"file": (path, f)}
        requests.post(url, files=files)


# --------------------------
# Main CLI
# --------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Networked bidirectional syncer")
    parser.add_argument("--folder", required=True, help="Local folder to sync")
    parser.add_argument("--log", action="store_true", help="Enable logging")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview actions without transferring")
    parser.add_argument("--ignore", default=".syncignore",
                        help="Ignore file in project")
    parser.add_argument("--server", action="store_true",
                        help="Run as server only")
    parser.add_argument(
        "--client", help="Run as client and connect to this peer URL")
    parser.add_argument("--port", type=int, default=8000,
                        help="Server port (default 8000)")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    ignore_patterns = load_files_to_ignore(folder / args.ignore)

    if args.server:
        start_server(folder, args.port)
    elif args.client:
        # Manual client mode
        sync_with_peer(folder, args.client, ignore_patterns,
                       dry_run=args.dry_run, log=args.log)
    else:
        # Auto mode (placeholder for LAN discovery)
        print(
            "[INFO] Auto-discovery not yet implemented. Use --server and \
            --client for now.")
        print("[INFO] Running as server for testing.")
        server_thread = threading.Thread(
            target=start_server, args=(folder, args.port), daemon=True)
        server_thread.start()
        input("[PRESS ENTER to exit]\n")


if __name__ == "__main__":
    main()
