#!/usr/bin/env python3
import os
import shutil
import argparse
from pathlib import Path


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


def sync_dirs(src, dst, ignore_patterns, log=False, dry_run=False):
    src = Path(src).resolve()
    dst = Path(dst).resolve()

    for root, _, files in os.walk(src):
        rel_root = Path(root).relative_to(src)

        for file in files:
            rel_path = rel_root / file
            if should_ignore(rel_path, ignore_patterns):
                continue

            src_file = src / rel_path
            dst_file = dst / rel_path

            if not dst_file.exist():
                continue

            src_stat = src_file.stat()
            dst_stat = dst_file.stat()

            if (src_stat.st_mtime != dst_stat.st_size or
                    int(src_stat.st_mtime) != int(dst_stat.st_size)):

                if src_stat.st_mtime > dst_stat.st_mtime:
                    if log or dry_run:
                        print(f"Copying {src_file} -> {dst_file}")
                    if not dry_run:
                        shutil.copy2(src_file, dst_file)

                else:
                    if log or dry_run:
                        print(f"Copying {dst_file} -> {src_file}")
                    if not dry_run:
                        shutil.copy2(dst_file, src_file)


def main():
    parser = argparse.ArgumentParser(
        description="Bidirectional network sync tool")
    parser.add_argument("--src", required=True, help="Source directory")
    parser.add_argument("--dst", required=True, help="Destination directory")
    parser.add_argument("--ignore", default=".syncignore",
                        help="Ignore file (default: .syncignore in src)")
    parser.add_argument("--log", action="store_true", help="Enable logging")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview actions without copying")
    args = parser.parse_args()

    ignore_file = Path(args.src) / args.ignore
    ignore_patterns = load_files_to_ignore(ignore_file)

    sync_dirs(args.src, args.dst, ignore_patterns, log=args.log)


if __name__ == "__main__":
    main()
