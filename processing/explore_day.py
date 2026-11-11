#!/usr/bin/env python3
"""First look at one day of collected ZTM data.

Answers: how many snapshots are damaged, whether realtime trips match the timetable,
whether stop_sequence advances along a trip, how large the reported delays are,
and prints one trip step by step.

Usage: python explore_day.py 2026-11-05     (a UTC date folder in ~/ztm_data/rt)
"""
import sys, os, csv, io, glob, zipfile, statistics, datetime as dt
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo
from google.transit import gtfs_realtime_pb2

DATA = os.environ.get("ZTM_DATA", os.path.expanduser("~/ztm_data"))
DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-11-05"
TZ = ZoneInfo("Europe/Warsaw")


def part(title):
    print("\n" + "=" * 60 + "\n" + title + "\n" + "=" * 60)


def local(ts):
    return dt.datetime.fromtimestamp(ts, TZ).strftime("%H:%M:%S")


def mmss(sec):
    sign = "-" if sec < 0 else "+"
    sec = abs(int(sec))
    return f"{sign}{sec // 60}:{sec % 60:02d}"


# ---------- 1. Read all snapshots of the day ----------
part(f"1. READING SNAPSHOTS FOR {DAY} (UTC)")
files = sorted(glob.glob(f"{DATA}/rt/{DAY}/*.pb"))
print(f"Snapshots: {len(files)}. Reading (1-3 minutes)", end="", flush=True)

last = {}                       # trip_id -> (stop_sequence, delay) seen last time
changes = defaultdict(list)     # trip_id -> rows when stop or delay changed
seqs = defaultdict(set)         # trip_id -> all stop_sequence values seen
route_of = {}
delay_min = Counter()           # delay rounded to minutes -> number of observations
vp_fields = Counter()
n_obs = 0
first_ts = last_ts = None
bad = []                        # damaged snapshots (downloaded incompletely)
sizes = []

for i, path in enumerate(files):
    f = gtfs_realtime_pb2.FeedMessage()
    raw = b""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        f.ParseFromString(raw)
    except Exception:
        bad.append((os.path.basename(path), len(raw)))
        continue
    sizes.append(len(raw))
    ts = f.header.timestamp
    first_ts = first_ts or ts
    last_ts = ts
    pos = {}
    for e in f.entity:
        if e.HasField("vehicle"):
            v = e.vehicle
            pos[v.vehicle.id] = (v.position.latitude, v.position.longitude)
            if i % 50 == 0:
                vp_fields["vehicles sampled"] += 1
                for fld in ("current_stop_sequence", "stop_id", "current_status"):
                    if v.HasField(fld):
                        vp_fields[fld] += 1
    for e in f.entity:
        if not e.HasField("trip_update") or not e.trip_update.stop_time_update:
            continue
        t = e.trip_update
        s = t.stop_time_update[0]
        if not (s.HasField("arrival") and s.arrival.HasField("delay")):
            continue
        tid, seq, d = t.trip.trip_id, s.stop_sequence, s.arrival.delay
        n_obs += 1
        delay_min[round(d / 60)] += 1
        seqs[tid].add(seq)
        route_of[tid] = t.trip.route_id
        if last.get(tid) != (seq, d):
            last[tid] = (seq, d)
            changes[tid].append((ts, seq, d, t.vehicle.id) + pos.get(t.vehicle.id, (None, None)))
    if i % 500 == 0:
        print(".", end="", flush=True)

print()
if not files:
    sys.exit("No snapshots for this day. Check the date.")
print(f"Damaged snapshots (skipped): {len(bad)} of {len(files)} ({len(bad) / len(files):.1%})")
if bad:
    print(f"  typical snapshot size ~{statistics.median(sizes) // 1024} KB; damaged examples: "
          + ", ".join(f"{n} ({s // 1024} KB)" for n, s in bad[:5]))
print(f"Snapshot time range (Poland local time): {local(first_ts)} - {local(last_ts)}")
print(f"Trip+delay observations: {n_obs:,}; distinct trips: {len(seqs):,}")

# ---------- 2. Timetable of that day ----------
part("2. MATCHING WITH THE TIMETABLE")
zips = sorted(glob.glob(f"{DATA}/gtfs/*.zip"))
zpath = max([z for z in zips if os.path.basename(z)[:10] <= DAY] or zips)
z = zipfile.ZipFile(zpath)
print(f"Timetable file: {os.path.basename(zpath)}")


def rows(name):
    return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig", errors="replace"))


example = max(seqs, key=lambda k: (len(seqs[k]), len(changes[k])))
n_stops = Counter()
example_stops = {}
for r in rows("stop_times.txt"):
    tid = r["trip_id"]
    if tid in seqs:
        n_stops[tid] += 1
        if tid == example:
            example_stops[int(r["stop_sequence"])] = r["stop_id"]
wanted = set(example_stops.values())
names = {r["stop_id"]: r["stop_name"] for r in rows("stops.txt") if r["stop_id"] in wanted}
short = {r["route_id"]: r["route_short_name"] for r in rows("routes.txt")}
found = [t for t in seqs if n_stops[t]]
print(f"Realtime trips found in the timetable: {len(found):,} of {len(seqs):,}")

# ---------- 3. Does the stop number move along the trip? ----------
part("3. DOES stop_sequence ADVANCE ALONG A TRIP?")
distinct = [len(seqs[t]) for t in found]
cover = [len(seqs[t]) / n_stops[t] for t in found]
one = sum(x == 1 for x in distinct) / len(distinct)
print(f"Distinct stop_sequence values per trip: median {statistics.median(distinct):.0f}, max {max(distinct)}")
print(f"Trips where stop_sequence never changed: {one:.0%}")
print(f"Share of a trip's stops observed: median {statistics.median(cover):.0%}; "
      f"trips with >=80% of stops observed: {sum(c >= 0.8 for c in cover) / len(cover):.0%}")
print(f"Fields present in vehicle positions (sample): {dict(vp_fields)}")
if statistics.median(distinct) >= 5 and statistics.median(cover) >= 0.6:
    print("RESULT: stop_sequence advances along trips - delays are visible at almost every stop, "
          "so a trip x stop delay table can be built directly from the feed.")
elif one > 0.8:
    print("RESULT: stop_sequence barely changes - stops would have to be inferred from vehicle coordinates.")
else:
    print("RESULT: mixed picture - needs a closer look.")

# ---------- 4. How big are the delays? ----------
part("4. HOW LARGE ARE THE DELAYS (all raw observations of the day)")
total = sum(delay_min.values())


def pct(p):
    acc = 0
    for m in sorted(delay_min):
        acc += delay_min[m]
        if acc >= p * total:
            return m


print(f"Median: {pct(0.5)} min; 90% of observations between {pct(0.05)} and {pct(0.95)} min")
in_window = sum(c for m, c in delay_min.items() if -1 <= m <= 3) / total
print(f"Share within -1..+3 min: {in_window:.0%}")
print(f"More than 1 min early: {sum(c for m, c in delay_min.items() if m < -1) / total:.1%}")
print(f"More than 10 min late: {sum(c for m, c in delay_min.items() if m > 10) / total:.1%}; "
      f"more than 30 min: {sum(c for m, c in delay_min.items() if m > 30) / total:.2%}")

# ---------- 5. One trip, step by step ----------
part("5. EXAMPLE: ONE TRIP STEP BY STEP")
ch = changes[example]
print(f"Line {short.get(route_of[example], route_of[example])}, trip {example}, "
      f"vehicle {ch[0][3]}, stops in timetable: {n_stops[example]}")
print("time     | seq    | stop                       | delay")
for ts, seq, d, veh, lat, lon in ch[:45]:
    name = names.get(example_stops.get(seq), "?")[:26]
    print(f"{local(ts)} | {seq:>6} | {name:<26} | {mmss(d)}")
if len(ch) > 45:
    print(f"... and {len(ch) - 45} more rows")

print("\nDone.")
