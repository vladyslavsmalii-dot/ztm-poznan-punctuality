#!/usr/bin/env python3
"""Turn raw ZTM snapshots into a compact table: one row per (trip run, stop).

For every trip run and every stop_sequence the vehicle reported, keeps:
when it was first/last seen at that stop number, the delay ZTM reported then,
and the vehicle position at those moments.

Usage:  python build_table.py      # processes every complete UTC day not processed yet
Output: ~/ztm_data/table/part_YYYY-MM-DD.csv.gz   (re-running skips finished days)
"""
import os, csv, gzip, glob, time, datetime as dt
from zoneinfo import ZoneInfo
from google.transit import gtfs_realtime_pb2

DATA = os.environ.get("ZTM_DATA", os.path.expanduser("~/ztm_data"))
OUT = f"{DATA}/table"
TZ = ZoneInfo("Europe/Warsaw")
GAP = 1800  # a trip not seen for 30 minutes is considered finished
COLS = ["run_date", "trip_id", "route_id", "vehicle_id", "stop_sequence",
        "first_seen", "last_seen", "n_obs", "delay_first", "delay_last",
        "lat_first", "lon_first", "lat_last", "lon_last"]

active = {}  # trip_id -> state of the run that is still going


def flush(trip_id, st, writer):
    run_date = dt.datetime.fromtimestamp(st["start"], TZ).strftime("%Y-%m-%d")
    for seq in sorted(st["stops"]):
        writer.writerow([run_date, trip_id, st["route"], st["veh"], seq] + st["stops"][seq])
    return len(st["stops"])


def main():
    os.makedirs(OUT, exist_ok=True)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    days = sorted(d for d in os.listdir(f"{DATA}/rt") if d < today)
    todo = [d for d in days if not os.path.exists(f"{OUT}/part_{d}.csv.gz")]
    print(f"Complete days: {len(days)}, already processed: {len(days) - len(todo)}, to do: {len(todo)}", flush=True)

    for k, day in enumerate(todo):
        t0 = time.time()
        tmp = f"{OUT}/part_{day}.csv.gz.tmp"
        fh = gzip.open(tmp, "wt", newline="", encoding="utf-8")
        w = csv.writer(fh)
        w.writerow(COLS)
        files = sorted(glob.glob(f"{DATA}/rt/{day}/*.pb"))
        bad = rows = 0
        ts = 0
        for i, path in enumerate(files):
            f = gtfs_realtime_pb2.FeedMessage()
            try:
                with open(path, "rb") as h:
                    f.ParseFromString(h.read())
            except Exception:
                bad += 1
                continue
            ts = f.header.timestamp
            pos = {}
            for e in f.entity:
                if e.HasField("vehicle"):
                    p = e.vehicle.position
                    pos[e.vehicle.vehicle.id] = (round(p.latitude, 5), round(p.longitude, 5))
            for e in f.entity:
                if not e.HasField("trip_update") or not e.trip_update.stop_time_update:
                    continue
                t = e.trip_update
                s = t.stop_time_update[0]
                if not (s.HasField("arrival") and s.arrival.HasField("delay")):
                    continue
                tid, seq, d, veh = t.trip.trip_id, s.stop_sequence, s.arrival.delay, t.vehicle.id
                st = active.get(tid)
                if st is not None and ts - st["last"] > GAP:  # same trip_id, but a new run (e.g. next day)
                    rows += flush(tid, active.pop(tid), w)
                    st = None
                if st is None:
                    st = active[tid] = {"start": ts, "last": ts, "route": t.trip.route_id, "veh": veh, "stops": {}}
                st["last"] = ts
                lat, lon = pos.get(veh, ("", ""))
                r = st["stops"].get(seq)
                if r is None:
                    st["stops"][seq] = [ts, ts, 1, d, d, lat, lon, lat, lon]
                else:
                    r[1], r[2], r[4], r[7], r[8] = ts, r[2] + 1, d, lat, lon
            if i % 200 == 0:  # write out trips that have finished
                for tid in [x for x, st in active.items() if ts - st["last"] > GAP]:
                    rows += flush(tid, active.pop(tid), w)
        if k == len(todo) - 1:  # last day of this run: write out everything that is left
            for tid in list(active):
                rows += flush(tid, active.pop(tid), w)
        fh.close()
        os.replace(tmp, f"{OUT}/part_{day}.csv.gz")
        print(f"{day}: snapshots {len(files)}, damaged {bad}, rows {rows:,}, {time.time() - t0:.0f} s", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
