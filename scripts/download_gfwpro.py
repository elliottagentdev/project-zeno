#!/usr/bin/env python3
"""
Download GFW Pro zarr datasets from S3 to /mnt/e/datasets/gfwpro/.
Uses parallel threads for speed (S3 has per-request latency overhead).
"""
import os
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import dotenv_values

ENV_PATH = "/mnt/e/agentdev/projects/project-zeno/.env"
DEST = Path("/mnt/e/datasets/gfwpro")
BUCKET = "gfwpro-users"
WORKERS = 32  # parallel download threads

DATASETS = [
    ("op-external-user/v2/sbtn.area.zarr",         "sbtn.area.zarr"),
    ("op-external-user/v2/jrc.area.zarr",           "jrc.area.zarr"),
    ("op-external-user/v2/mergedLoss.zarr",         "mergedLoss.zarr"),
    ("op-external-user/v3/intdist_date_conf.zarr",  "intdist_date_conf.zarr"),
]

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
    s3 = make_client(key, secret)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if local_path.exists() and local_path.stat().st_size == size:
        return size, True  # skipped (already present)
    s3.download_file(BUCKET, s3_key, str(local_path))
    return size, False  # downloaded

def sync_dataset(key, secret, prefix, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    s3 = make_client(key, secret)

    print(f"  Listing objects under {prefix}...", flush=True)
    objects = list_objects(s3, prefix + "/")
    total_bytes = sum(o["Size"] for o in objects)
    print(f"  {len(objects)} objects, {total_bytes/1024/1024:.1f} MB", flush=True)

    tasks = []
    for obj in objects:
        s3_key = obj["Key"]
        rel = s3_key[len(prefix):].lstrip("/")
        local_path = dest_dir / rel
        tasks.append((key, secret, s3_key, local_path, obj["Size"]))

    downloaded_bytes = 0
    skipped_bytes = 0
    done = 0
    start = time.time()
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(download_one, t): t for t in tasks}
        for future in as_completed(futures):
            size, skipped = future.result()
            with lock:
                done += 1
                if skipped:
                    skipped_bytes += size
                else:
                    downloaded_bytes += size
                if done % 500 == 0 or done == len(tasks):
                    elapsed = time.time() - start
                    rate = downloaded_bytes / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    pct = done / len(tasks) * 100
                    print(
                        f"  {done}/{len(tasks)} ({pct:.0f}%) — "
                        f"{(downloaded_bytes+skipped_bytes)/1024/1024:.0f}/{total_bytes/1024/1024:.0f} MB — "
                        f"{rate:.1f} MB/s — {elapsed:.0f}s elapsed",
                        flush=True
                    )

    elapsed = time.time() - start
    print(
        f"  Finished: {downloaded_bytes/1024/1024:.0f} MB downloaded, "
        f"{skipped_bytes/1024/1024:.0f} MB skipped (already present) in {elapsed:.0f}s",
        flush=True
    )
    return len(objects), total_bytes

def validate(dest_dir, name):
    meta = list(dest_dir.glob(".z*"))
    count = len(list(dest_dir.rglob("*")))
    if meta:
        print(f"  OK: {name} ({count} files)", flush=True)
        return True
    print(f"  FAIL: {name} missing zarr metadata (.zattrs / .zgroup)", flush=True)
    return False

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    key, secret = load_creds()

    total_files = 0
    total_bytes = 0

    for prefix, local_name in DATASETS:
        dest_dir = DEST / local_name
        print(f"\nDownloading {local_name}...", flush=True)
        n, b = sync_dataset(key, secret, prefix, dest_dir)
        total_files += n
        total_bytes += b

    print(f"\nAll datasets: {total_files} files, {total_bytes/1024/1024:.1f} MB total", flush=True)

    print("\nValidating zarr stores...", flush=True)
    ok = all(validate(DEST / name, name) for _, name in DATASETS)
    if not ok:
        print("\nERROR: Validation failed", flush=True)
        sys.exit(1)
    print("\nValidation PASSED", flush=True)

if __name__ == "__main__":
    main()
