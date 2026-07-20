#!/bin/bash
# Log a single row of system-stats to CSV. Called every 15 min by systemd timer.
# One row per invocation: ISO_UTC, load_1m, mem_used_pct, mem_used_mb, mem_total_mb, disk_used_pct, disk_used_gb, disk_total_gb
set -euo pipefail

CSV=/home/gdt/system_stats.csv
if [ ! -f "$CSV" ]; then
    echo "ts_utc,load_1m,mem_used_pct,mem_used_mb,mem_total_mb,disk_used_pct,disk_used_gb,disk_total_gb" > "$CSV"
fi

ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
load=$(cut -d' ' -f1 /proc/loadavg)

# Memory: parse /proc/meminfo (KB units). Available = the "actually usable" figure.
mem_total_kb=$(awk '/MemTotal:/ {print $2}' /proc/meminfo)
mem_avail_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
mem_used_kb=$((mem_total_kb - mem_avail_kb))
mem_used_mb=$((mem_used_kb / 1024))
mem_total_mb=$((mem_total_kb / 1024))
mem_used_pct=$(awk -v u="$mem_used_kb" -v t="$mem_total_kb" 'BEGIN{printf "%.1f", 100*u/t}')

# Disk: root filesystem
disk_line=$(df -B1 / | tail -1)
disk_used_b=$(echo "$disk_line" | awk '{print $3}')
disk_total_b=$(echo "$disk_line" | awk '{print $2}')
disk_used_pct=$(echo "$disk_line" | awk '{print $5}' | tr -d '%')
disk_used_gb=$(awk -v b="$disk_used_b" 'BEGIN{printf "%.2f", b/1024/1024/1024}')
disk_total_gb=$(awk -v b="$disk_total_b" 'BEGIN{printf "%.2f", b/1024/1024/1024}')

echo "$ts,$load,$mem_used_pct,$mem_used_mb,$mem_total_mb,$disk_used_pct,$disk_used_gb,$disk_total_gb" >> "$CSV"
