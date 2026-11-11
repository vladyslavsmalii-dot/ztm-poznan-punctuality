#!/usr/bin/env python3
"""ZTM Poznan GTFS-RT collector.
Every 20 s saves feeds.pb (vehicle positions + delays) as a raw file.
Once a day saves the static GTFS timetable and the vehicle dictionary.
All times in file names are UTC.
"""
import hashlib, os, time, datetime as dt, urllib.request

BASE = os.environ.get("ZTM_BASE", "https://www.ztm.poznan.pl/pl/dla-deweloperow")
RT_URL = BASE + "/getGtfsRtFile/?file=feeds.pb"
DAILY = [  # (folder, url, extension, first bytes that a valid file starts with)
    ("gtfs", BASE + "/getGTFSFile", "zip", b"PK"),
    ("vehicle_dictionary", BASE + "/getGtfsRtFile/?file=vehicle_dictionary.csv", "csv", b""),
]
DATA = os.environ.get("ZTM_DATA", os.path.expanduser("~/ztm_data"))
INTERVAL = 20          # seconds between realtime downloads
DAILY_RETRY = 1800     # if a daily download fails, retry after 30 min
HEADERS = {"User-Agent": "ztm-poznan-punctuality-study (student data project)"}


def log(msg):
    print(dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), msg, flush=True)


def fetch(url, timeout):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def daily_downloads(now, last_try):
    day = now.strftime("%Y-%m-%d")
    for folder, url, ext, magic in DAILY:
        path = f"{DATA}/{folder}/{day}.{ext}"
        if os.path.exists(path) or time.time() - last_try.get(folder, 0) < DAILY_RETRY:
            continue
        last_try[folder] = time.time()
        try:
            data = fetch(url, timeout=300)
            if not data.startswith(magic) or len(data) < 100:
                raise ValueError(f"unexpected content ({len(data)} bytes)")
            save(path, data)
            log(f"saved {folder}/{day}.{ext} ({len(data) // 1024} KB)")
        except Exception as e:
            log(f"ERROR {folder}: {e}")


def main():
    log(f"collector started, saving to {DATA}")
    last_hash, saved, errors, hour_start = None, 0, 0, time.time()
    last_try = {}
    next_t = time.time()
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            data = fetch(RT_URL, timeout=15)
            if not data.startswith(b"\n"):  # a GTFS-RT file always starts with its header block
                raise ValueError(f"not a GTFS-RT file ({len(data)} bytes)")
            h = hashlib.sha1(data).hexdigest()
            if h != last_hash:
                save(f"{DATA}/rt/{now:%Y-%m-%d}/{now:%H%M%S}.pb", data)
                last_hash = h
                saved += 1
        except Exception as e:
            errors += 1
            log(f"ERROR realtime: {e}")

        daily_downloads(now, last_try)

        if time.time() - hour_start >= 3600:
            log(f"last hour: saved {saved} snapshots, {errors} errors")
            saved, errors, hour_start = 0, 0, time.time()

        next_t += INTERVAL
        if next_t < time.time():  # fell behind (slow network) -> don't try to catch up
            next_t = time.time() + INTERVAL
        time.sleep(max(0, next_t - time.time()))


if __name__ == "__main__":
    main()
