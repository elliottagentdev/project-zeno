#!/usr/bin/env python3
"""
Download GFW Pro zarr datasets from S3 in throttled bursts.

Downloads in time-limited bursts with cooldown periods between them,
to avoid overheating a wifi card under sustained high-throughput load.
Resumes where it left off — files already downloaded (matching size) are skipped.
"""
import argparse
import os
import signal
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dotenv import dotenv_values

ENV_PATH = "/mnt/e/agentdev/projects/project-zeno/.env"
DEST = Path("/mnt/e/datasets/gfwpro")
BUCKET = "gfwpro-users"

DATASETS = [
    ("op-external-user/v2/sbtn.area.zarr",        "sbtn.area.zarr"),
    ("op-external-user/v2/jrc.area.zarr",          "jrc.area.zarr"),
    ("op-external-user/v2/mergedLoss.zarr",        "mergedLoss.zarr"),
    ("op-external-user/v3/intdist_date_conf.zarr", "intdist_date_conf.zarr"),
]

# Graceful shutdown flag
_shutdown = False


def handle_sigint(signum, frame):
    global _shutdown
    _shutdown = True
    print("\nCtrl+C received — draining in-flight downloads...", flush=True)


def parse_args():
    p = argparse.ArgumentParser(
        description="Download GFW Pro zarr datasets with throttled bursts"
    )
    p.add_argument(
        "--burst", type=int, default=90,
        help="Burst duration in seconds (default: 90)",
    )
    p.add_argument(
        "--cooldown", type=int, default=45,
        help="Cooldown duration in seconds (default: 45)",
    )
    p.add_argument(
        "--workers", type=int, default=8,
        help="Parallel download threads (default: 8)",
    )
    return p.parse_args()


def load_creds():
    env = dotenv_values(ENV_PATH)
    key = env.get("AWS_ACCESS_KEY_ID", "")
    secret = env.get("AWS_SECRET_ACCESS_KEY", "")
    if not key or not secret:
        print("ERROR: AWS credentials not found in .env", flush=True)
        sys.exit(1)
    return key, secret


def make_client(key, secret):
    import boto3
    return boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name="us-east-1",
    )


def list_objects(s3, prefix):
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return objects


def download_one(args):
    key, secret, s3_key, local_path, size = args
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if local_path.exists() and local_path.stat().st_size == size:
        return size, True  # skipped
    s3 = make_client(key, secret)
    s3.download_file(BUCKET, s3_key, str(local_path))
    return size, False  # downloaded


def validate(dest_dir, name):
    """Check for zarr metadata (v2: .zattrs/.zgroup, v3: zarr.json)."""
    has_v2 = bool(list(dest_dir.glob(".z*")))
    has_v3 = (dest_dir / "zarr.json").exists()
    count = len(list(dest_dir.rglob("*")))
    if has_v2 or has_v3:
        print(f"  OK: {name} ({count} files)", flush=True)
        return True
    print(f"  FAIL: {name} missing zarr metadata", flush=True)
    return False


def gather_all_tasks(key, secret):
    """List all S3 objects across all datasets, return flat task list."""
    s3 = make_client(key, secret)
    all_tasks = []
    for prefix, local_name in DATASETS:
        dest_dir = DEST / local_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Listing {local_name}...", end=" ", flush=True)
        objects = list_objects(s3, prefix + "/")
        total_bytes = sum(o["Size"] for o in objects)
        print(
            f"{len(objects)} objects, {total_bytes / 1024 / 1024 / 1024:.2f} GB",
            flush=True,
        )
        for obj in objects:
            s3_key = obj["Key"]
            rel = s3_key[len(prefix):].lstrip("/")
            local_path = dest_dir / rel
            all_tasks.append((key, secret, s3_key, local_path, obj["Size"]))
    return all_tasks


def filter_pending(tasks):
    """Filter out tasks where the local file already exists with correct size."""
    pending = []
    for t in tasks:
        _, _, _, local_path, size = t
        if not local_path.exists() or local_path.stat().st_size != size:
            pending.append(t)
    return pending


def run_burst(pending_tasks, workers, burst_seconds):
    """Run a time-bounded download burst.

    Uses wait(FIRST_COMPLETED) in a loop so new tasks are continuously
    fed to the pool for the full burst duration.

    Returns (consumed, dl_count, dl_bytes, skipped).
    """
    deadline = time.monotonic() + burst_seconds
    downloaded_count = 0
    downloaded_bytes = 0
    skipped_count = 0
    consumed = 0
    task_iter = iter(pending_tasks)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = set()

        # Seed the pool
        for _ in range(min(workers * 2, len(pending_tasks))):
            task = next(task_iter, None)
            if task is None:
                break
            active.add(pool.submit(download_one, task))
            consumed += 1

        while active:
            # Wait for at least one to complete
            done, active = wait(active, return_when=FIRST_COMPLETED)

            for future in done:
                size, was_skipped = future.result()
                if was_skipped:
                    skipped_count += 1
                else:
                    downloaded_count += 1
                    downloaded_bytes += size

            # Submit replacements if still within burst window
            if time.monotonic() < deadline and not _shutdown:
                for _ in range(len(done)):
                    task = next(task_iter, None)
                    if task is None:
                        break
                    active.add(pool.submit(download_one, task))
                    consumed += 1

    return consumed, downloaded_count, downloaded_bytes, skipped_count


def main():
    args = parse_args()
    signal.signal(signal.SIGINT, handle_sigint)

    print("=" * 60)
    print("GFW PRO ZARR DOWNLOAD — THROTTLED")
    print(f"  Burst: {args.burst}s | Cooldown: {args.cooldown}s | Workers: {args.workers}")
    print("=" * 60)

    # Load credentials and list all S3 objects
    key, secret = load_creds()
    print("\nListing S3 objects...", flush=True)
    all_tasks = gather_all_tasks(key, secret)
    print(f"\nTotal S3 objects: {len(all_tasks)}", flush=True)

    # Filter to pending
    print("Scanning local files for resume state...", flush=True)
    pending = filter_pending(all_tasks)
    total_pending_bytes = sum(t[4] for t in pending)
    print(
        f"Pending: {len(pending)} files, "
        f"{total_pending_bytes / 1024 / 1024 / 1024:.2f} GB\n",
        flush=True,
    )

    if not pending:
        print("Nothing to download — all files present and correct.")
    else:
        offset = 0
        cycle = 0
        total_dl_bytes = 0
        total_dl_files = 0
        start_time = time.monotonic()

        while offset < len(pending) and not _shutdown:
            cycle += 1
            remaining = len(pending) - offset
            print(
                f"[Cycle {cycle}] Starting burst — "
                f"{remaining} files remaining...",
                flush=True,
            )

            burst_start = time.monotonic()
            consumed, dl_count, dl_bytes, skipped = run_burst(
                pending[offset:], args.workers, args.burst,
            )
            burst_elapsed = time.monotonic() - burst_start
            offset += consumed
            total_dl_bytes += dl_bytes
            total_dl_files += dl_count

            rate = dl_bytes / burst_elapsed / 1024 / 1024 if burst_elapsed > 0 else 0
            remaining_after = len(pending) - offset
            print(
                f"[Cycle {cycle}] Burst: {burst_elapsed:.0f}s | "
                f"Downloaded: {dl_count} files ({dl_bytes / 1024 / 1024:.1f} MB) | "
                f"Skipped: {skipped} | "
                f"Rate: {rate:.1f} MB/s | "
                f"Remaining: ~{remaining_after} files",
                flush=True,
            )

            if offset >= len(pending):
                break
            if _shutdown:
                break

            print(f"Cooldown: {args.cooldown}s...", flush=True)
            # Interruptible cooldown
            for _ in range(args.cooldown):
                if _shutdown:
                    break
                time.sleep(1)
            print("", flush=True)

        elapsed_total = time.monotonic() - start_time
        print(
            f"\nSession complete: {total_dl_files} files, "
            f"{total_dl_bytes / 1024 / 1024 / 1024:.2f} GB downloaded "
            f"in {elapsed_total / 60:.1f} minutes "
            f"({cycle} cycles)",
            flush=True,
        )

    # Validate
    print("\nValidating zarr stores...", flush=True)
    ok = all(
        validate(DEST / name, name)
        for _, name in DATASETS
        if (DEST / name).exists()
    )
    if not ok:
        print("\nWARNING: Validation issues detected (may be incomplete download)")
    else:
        print("\nValidation PASSED")


if __name__ == "__main__":
    main()
