#!/usr/bin/env bash
# ==============================================================================
# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

# ==============================================================================
# make_results.sh - every table and figure of the recorded experiments.
#
# Runs the analysis scripts of scripts/metrics on the recordings and writes
# their output to results/. Read-only on the bags: it records nothing and
# starts no ROS node. One step per output:
#
#   step        script                 recordings            output
#   full        analyze_campaign.py    campaigns full and    results/full/
#                                      full-repeat
#   faults      analyze_faults.py      campaign faults       results/faults/
#   forge       analyze_faults.py      campaign forge        results/forge/
#   forge-obs   analyze_campaign.py    campaign forge-obs    results/forge-obs/
#   clock       analyze_clock.py       bench clock           results/clock-bench/clock/
#   auth-delay  analyze_campaign.py    campaign auth-delay   results/auth-delay/
#   t3-window   analyze_campaign.py    campaign t3-window    results/t3-window/
#   scaling     analyze_campaign.py    campaign scaling      results/scaling/
#   fleet       analyze_scaling.py     campaign scaling      results/scaling/
#   figures     plot_figures.py        three runs (FIGURE_*) results/figures/
#   audit       audit_recordings.py    the recordings of     results/audit_recordings.csv
#                                      AUDITED in bags/      and _veto.csv
#
# The campaigns are in bags/campaigns, the bench in bags/clock-bench. A step
# whose recordings are missing is skipped; the steps that were skipped or
# failed are named at the end. What each script prints, the tables included,
# goes to results/logs/<step>.log.
#
# Usage:
#   source /opt/ros/humble/setup.bash && source install/setup.bash
#   ./scripts/metrics/make_results.sh
#
# Variables: BAGS_DIR (default bags), RESULTS_DIR (default results).
# Exit codes: 0 every step done, 1 a step skipped or failed, 2 cannot start.
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/../.." || exit 2

BAGS_DIR="${BAGS_DIR:-bags}"
RESULTS_DIR="${RESULTS_DIR:-results}"
CAMPAIGNS="$BAGS_DIR/campaigns"
METRICS="scripts/metrics"
LOGS="$RESULTS_DIR/logs"

# The recordings made before the campaigns that the audit reads: the bag
# folders of bags/ named <group>-YYYYMMDD-HHMMSS, for these groups.
AUDITED=(coastal civilian deny stale-eo vec-frontal vec-east-deep vec-rear
         loss-none loss-radar loss-rf loss-acoustic loss-eo veto b2-check)

# The runs of the figures, all recorded with the same version of the code.
FIGURE_NOMINAL="$CAMPAIGNS/auth-delay/nominal/run-01-seed1000/bag"
FIGURE_FAULT="$CAMPAIGNS/faults/fault-worker/run-01-seed1000/bag"
FIGURE_GATE="$CAMPAIGNS/faults/fault-gate/run-01-seed1000/bag"

log() { echo "[results] $*"; }
die() { log "$*"; exit 2; }

python3 -c "import rosbag2_py" 2>/dev/null ||
  die "cannot import rosbag2_py: run 'source /opt/ros/humble/setup.bash && source install/setup.bash' first."
[ -d "$BAGS_DIR" ] || die "no $BAGS_DIR folder: set BAGS_DIR."
mkdir -p "$LOGS" || die "cannot write to $RESULTS_DIR."

DONE=()
SKIPPED=()
FAILED=()

# step NAME RECORDING... -- COMMAND...
# Runs COMMAND, with its output in logs/NAME.log, if every RECORDING exists;
# otherwise skips the step.
step() {
  local name="$1" missing=() start rc
  shift
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    [ -e "$1" ] || missing+=("$1")
    shift
  done
  shift
  if [ ${#missing[@]} -gt 0 ]; then
    log "$name: skipped, not found: ${missing[*]}"
    SKIPPED+=("$name")
    return
  fi
  log "$name: $(basename "$2") ..."
  start=$SECONDS
  if "$@" > "$LOGS/$name.log" 2>&1; then
    log "$name: done in $((SECONDS - start)) s"
    DONE+=("$name")
  else
    rc=$?
    log "$name: failed (exit $rc), see $LOGS/$name.log"
    FAILED+=("$name")
  fi
}

step full "$CAMPAIGNS/full" "$CAMPAIGNS/full-repeat" -- \
  python3 "$METRICS/analyze_campaign.py" "$CAMPAIGNS/full" \
  "$CAMPAIGNS/full-repeat" --out "$RESULTS_DIR/full"
step faults "$CAMPAIGNS/faults" -- \
  python3 "$METRICS/analyze_faults.py" "$CAMPAIGNS/faults" \
  --out "$RESULTS_DIR/faults"
step forge "$CAMPAIGNS/forge" -- \
  python3 "$METRICS/analyze_faults.py" "$CAMPAIGNS/forge" \
  --out "$RESULTS_DIR/forge"
step forge-obs "$CAMPAIGNS/forge-obs" -- \
  python3 "$METRICS/analyze_campaign.py" "$CAMPAIGNS/forge-obs" \
  --out "$RESULTS_DIR/forge-obs"
step clock "$BAGS_DIR/clock-bench/clock" -- \
  python3 "$METRICS/analyze_clock.py" "$BAGS_DIR/clock-bench/clock" \
  --out "$RESULTS_DIR/clock-bench/clock"
step auth-delay "$CAMPAIGNS/auth-delay" -- \
  python3 "$METRICS/analyze_campaign.py" "$CAMPAIGNS/auth-delay" \
  --out "$RESULTS_DIR/auth-delay"
step t3-window "$CAMPAIGNS/t3-window" -- \
  python3 "$METRICS/analyze_campaign.py" "$CAMPAIGNS/t3-window" \
  --out "$RESULTS_DIR/t3-window"
step scaling "$CAMPAIGNS/scaling" -- \
  python3 "$METRICS/analyze_campaign.py" "$CAMPAIGNS/scaling" \
  --out "$RESULTS_DIR/scaling"
step fleet "$CAMPAIGNS/scaling" -- \
  python3 "$METRICS/analyze_scaling.py" "$CAMPAIGNS/scaling" \
  --out "$RESULTS_DIR/scaling"
step figures "$FIGURE_NOMINAL" "$FIGURE_FAULT" "$FIGURE_GATE" -- \
  python3 "$METRICS/plot_figures.py" --nominal "$FIGURE_NOMINAL" \
  --fault "$FIGURE_FAULT" --gate "$FIGURE_GATE" --out "$RESULTS_DIR/figures"

audited=()
shopt -s nullglob
for group in "${AUDITED[@]}"; do
  audited+=("$BAGS_DIR/$group"-[0-9]*)
done
shopt -u nullglob
if [ ${#audited[@]} -eq 0 ]; then
  log "audit: skipped, no recording of ${AUDITED[*]} in $BAGS_DIR"
  SKIPPED+=(audit)
else
  step audit "${audited[@]}" -- \
    python3 "$METRICS/audit_recordings.py" "${audited[@]}" \
    --csv "$RESULTS_DIR/audit_recordings.csv"
fi

log "done: ${#DONE[@]} step(s), results in $RESULTS_DIR/, logs in $LOGS/"
[ ${#SKIPPED[@]} -eq 0 ] || log "skipped: ${SKIPPED[*]}"
[ ${#FAILED[@]} -eq 0 ] || log "failed: ${FAILED[*]}"
[ ${#SKIPPED[@]} -eq 0 ] && [ ${#FAILED[@]} -eq 0 ] || exit 1