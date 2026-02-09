#!/bin/bash
# Live progress tracker — active processes only, per-worker progress bars
# Flicker-free: tput home + overwrite instead of clear

DB="/Users/laeh/Github/MADphotos/images/mad_photos.db"
TOTAL=9011
tput civis 2>/dev/null
trap 'tput cnorm 2>/dev/null; exit' INT TERM

mk_bar() {
    local cur=$1 max=$2 width=${3:-40}
    local filled=$((cur * width / max))
    local bar=""
    for ((j=0; j<width; j++)); do
        if [ "$j" -lt "$filled" ]; then bar+="█"; else bar+="░"; fi
    done
    echo "$bar"
}

clear
while true; do
    BUF=""

    # Overall Florence progress
    FC=$(sqlite3 "$DB" "SELECT COUNT(*) FROM florence_captions;" 2>/dev/null)
    FC_PCT=$((FC * 100 / TOTAL))
    FC_REM=$((TOTAL - FC))
    FC_BAR=$(mk_bar "$FC" "$TOTAL" 50)

    BUF+="╔════════════════════════════════════════════════════════════════════╗\n"
    BUF+="║              MADphotos — Active Process Monitor                  ║\n"
    BUF+="╚════════════════════════════════════════════════════════════════════╝\n"
    BUF+="\n"
    BUF+="  FLORENCE CAPTIONS   ${FC} / ${TOTAL}   ${FC_PCT}%%   (${FC_REM} remaining)\n"
    BUF+="  ${FC_BAR}\n"
    BUF+="\n"
    BUF+="  ──────────────────────────────────────────────────────────────────\n"

    HAS=0
    for logfile in /tmp/florence_w*.log; do
        [ -f "$logfile" ] || continue
        wnum=$(basename "$logfile" .log | sed 's/florence_w//')
        pid=$(pgrep -f "florence_worker.*--worker ${wnum}" 2>/dev/null | head -1)
        [ -z "$pid" ] && continue
        HAS=1

        cpu=$(ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' ')
        last=$(grep -E "W[0-9]:" "$logfile" 2>/dev/null | tail -1)

        # Parse: W0: 200/1050 done=200 err=0 0.29/s ~2941s
        w_done=$(echo "$last" | grep -oE 'done=[0-9]+' | cut -d= -f2)
        w_total=$(echo "$last" | grep -oE '[0-9]+/[0-9]+' | head -1 | cut -d/ -f2)
        w_rate=$(echo "$last" | grep -oE '[0-9]+\.[0-9]+/s' | head -1)
        w_eta=$(echo "$last" | grep -oE '~[0-9]+s' | head -1)
        w_err=$(echo "$last" | grep -oE 'err=[0-9]+' | cut -d= -f2)

        # Detect device from command line
        cmdline=$(ps -p "$pid" -o args= 2>/dev/null)
        if echo "$cmdline" | grep -q "device mps"; then
            dev="MPS"
        else
            dev="CPU"
        fi

        if [ -n "$w_done" ] && [ -n "$w_total" ] && [ "$w_total" -gt 0 ] 2>/dev/null; then
            w_pct=$((w_done * 100 / w_total))
            w_bar=$(mk_bar "$w_done" "$w_total" 30)
            BUF+="  W${wnum} [${dev}]  ${w_bar}  ${w_done}/${w_total}  ${w_pct}%%"
            [ -n "$w_rate" ] && BUF+="  ${w_rate}"
            [ -n "$w_eta" ] && BUF+="  ${w_eta}"
            [ -n "$w_err" ] && [ "$w_err" != "0" ] && BUF+="  err:${w_err}"
            BUF+="  cpu:${cpu}%%\n"
        else
            BUF+="  W${wnum} [${dev}]  loading model...  cpu:${cpu}%%\n"
        fi
    done

    # signals_v2
    for pid in $(pgrep -f "signals_v2.py" 2>/dev/null); do
        HAS=1
        cpu=$(ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' ')
        BUF+="  signals_v2  cpu:${cpu}%%\n"
    done

    # vectors_v2
    for pid in $(pgrep -f "vectors_v2.py" 2>/dev/null); do
        HAS=1
        cpu=$(ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' ')
        last=$(grep -E "[0-9]+/" /tmp/mad_vectors_v2.log 2>/dev/null | tail -1)
        v_done=$(echo "$last" | grep -oE '^[[:space:]]*[0-9]+' | tr -d ' ')
        v_total=$(echo "$last" | grep -oE '[0-9]+/[0-9]+' | head -1 | cut -d/ -f2)
        if [ -n "$v_done" ] && [ -n "$v_total" ] && [ "$v_total" -gt 0 ] 2>/dev/null; then
            v_bar=$(mk_bar "$v_done" "$v_total" 30)
            v_pct=$((v_done * 100 / v_total))
            BUF+="  vectors_v2  ${v_bar}  ${v_done}/${v_total}  ${v_pct}%%  cpu:${cpu}%%\n"
        else
            BUF+="  vectors_v2  loading...  cpu:${cpu}%%\n"
        fi
    done

    [ "$HAS" -eq 0 ] && BUF+="  (no active workers)\n"

    BUF+="\n"
    BUF+="  ──────────────────────────────────────────────────────────────────\n"

    TOTAL_CPU=$(ps aux | grep -E "florence_worker|signals_v2|vectors_v2|_rembg" | grep -v grep | awk '{sum+=$3} END {printf "%.0f", sum}')
    WORKER_COUNT=$(pgrep -c -f "florence_worker|signals_v2|vectors_v2" 2>/dev/null)

    BUF+="  ${WORKER_COUNT} workers  |  Total CPU: ${TOTAL_CPU:-0}%%  |  $(date '+%H:%M:%S')\n"
    BUF+="                                                                       \n"

    tput home 2>/dev/null
    printf "$BUF"
    tput ed 2>/dev/null

    sleep 5
done
