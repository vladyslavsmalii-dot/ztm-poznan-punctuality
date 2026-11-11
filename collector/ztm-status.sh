#!/bin/bash
# Quick health check of the collector. Installed as /usr/local/bin/ztm-status.
D="$HOME/ztm_data"
T=$(date -u +%Y-%m-%d)
echo "Collector service: $(systemctl is-active ztm-collector)"
echo "Snapshots today (UTC): $(ls "$D/rt/$T" 2>/dev/null | wc -l)  (a full day is ~4300)"
echo "Latest snapshot: $(ls "$D/rt/$T" 2>/dev/null | tail -1)  (UTC)"
echo "Days with data: $(ls "$D/rt" 2>/dev/null | wc -l)"
echo "Timetables saved: $(ls "$D/gtfs" 2>/dev/null | wc -l)"
echo "Data size: $(du -sh "$D" 2>/dev/null | cut -f1)"
echo "Free disk: $(df -h / | awk 'NR==2{print $4}')"
echo "--- latest collector messages ---"
sudo journalctl -u ztm-collector -n 5 --no-pager -o cat
