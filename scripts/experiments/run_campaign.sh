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
# run_campaign.sh - run a campaign of recorded pipeline runs.
#
# A campaign is a set of configurations (scripts/experiments/configurations.conf)
# with RUNS runs each. For every run the scenario is started from scratch
# (scripts/sim/coastal_up.sh), one pipeline run is recorded
# (scripts/record/record_run.sh, which ends on its own once the result is in),
# the logs are copied next to the bag, and the scenario is stopped again
# (scripts/sim/coastal_down.sh). Restarting the scenario puts every run in the
# same initial state: the vehicles at their spawn points, the EO camera
# (carried by UAV0) at its post, the rover at the start of its patrol.
#
# Runs alternate between the configurations (run 1 of each, then run 2 of
# each, ...), so that a campaign stopped halfway is balanced, and anything that
# drifts during a session affects every configuration alike. Run n has the
# same seed in every configuration, FIRST_SEED + 10*(n-1): the step of 10
# keeps the runs apart, since each run also gives SEED+1 to SEED+4 to the
# sensing agents.
#
# SESSIONS
# ========
# A campaign can be stopped at any moment and continued later with the same
# command: each session does the runs that are still missing. Nothing is ever
# overwritten: every attempt has its own folder and its own line in the
# manifest.
#   - Ctrl-C closes the run in progress cleanly, stops the scenario and ends
#     the session. That run is recorded as interrupted and is redone, with the
#     same seed, in the next session.
#   - MAX_HOURS ends the session once that many hours have passed: the run in
#     progress is completed, no new one is started.
#   - A run is done once it has a valid outcome. An attempt whose scenario does
#     not start, or that a guard refuses or stops, is repeated at once with the
#     same seed. After MAX_ATTEMPTS failed attempts in a row the run is put
#     aside for the rest of the session, and the next session tries it again:
#     no run is given up, so every configuration reaches RUNS valid runs. Two
#     runs put aside one after the other stop the session: then the problem
#     is the set-up, not the run.
#   - The session also stops if the scenario does not stop cleanly after a run:
#     the next run would not start from a clean state.
#
# Usage:
#   ./scripts/experiments/run_campaign.sh <campaign> [configuration ...]
#
#   ./scripts/experiments/run_campaign.sh full                   # every configuration
#   MAX_HOURS=3 ./scripts/experiments/run_campaign.sh full       # a 3-hour session
#   RUNS=2 ./scripts/experiments/run_campaign.sh pilot nominal deny
#
# Variables:
#   RUNS          runs per configuration                        default 20
#   FIRST_SEED    seed of run 1                                 default 1000
#   MAX_HOURS     length of the session, in hours               default none
#   MAX_ATTEMPTS  failed attempts before a run is put aside     default 3
#   HEADLESS      1 = Gazebo without its window                 default 0
#   ALLOW_NEW_COMMIT  1 = continue on another commit            default 0
#
# Output, under bags/campaigns/<campaign>/:
#   manifest.csv                         one line per attempt
#   campaign.env                         first seed and commit of the campaign
#   <configuration>/run-NN-seedS/        bag/ (the rosbag2 bag) and logs/
#   <configuration>/run-NN-seedS-tryK/   a later attempt of the same run
#
# Exit codes: 0 the session ended (campaign complete or MAX_HOURS reached);
# 1 the campaign cannot start, or the session needs a look (runs put aside,
# two of them in a row, a scenario that does not stop); 130 stopped with
# Ctrl-C.
# ==============================================================================
set -o pipefail
cd "$(dirname "$0")/../.." || exit 1
source install/setup.bash

CONFIG_FILE="scripts/experiments/configurations.conf"
CAMPAIGNS_DIR="bags/campaigns"
SEED_STEP=10
MIN_FREE_GB=10   # warn when less disk space than this is free

RUNS="${RUNS:-20}"
FIRST_SEED="${FIRST_SEED:-1000}"
MAX_HOURS="${MAX_HOURS:-}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
export HEADLESS="${HEADLESS:-0}"
export SIM_LOG_DIR="${SIM_LOG_DIR:-/tmp/gs_sim}"

# The three steps of a run. Overridable only to test this script.
COASTAL_UP="${COASTAL_UP:-./scripts/sim/coastal_up.sh}"
COASTAL_DOWN="${COASTAL_DOWN:-./scripts/sim/coastal_down.sh}"
RECORD_RUN="${RECORD_RUN:-./scripts/record/record_run.sh}"

# The variables a configuration may set, which are the scenario variables of
# test_pipeline.sh, each with the values it accepts (a regular expression). A
# wrong value stops the campaign before the first run, instead of producing
# runs of a scenario nobody asked for.
NUMBER='[0-9]+([.][0-9]+)?'
BOOLEAN='true|false'
declare -A KNOBS=(
  [ATTACK_VECTOR]='frontal|east-deep|rear|demo'
  [INTRUDER_DELAY]="$NUMBER"     [INTRUDER_SPEED]="$NUMBER"
  [RADAR_ENABLED]="$BOOLEAN"     [RF_ENABLED]="$BOOLEAN"
  [ACOUSTIC_ENABLED]="$BOOLEAN"  [EO_ENABLED]="$BOOLEAN"
  [EO_DELAY_S]="$NUMBER"         [RF_LABEL]='[A-Za-z]+'
  [EXPECT_THREAT]='yes|no'       [OBSERVE_S]="$NUMBER"
  [DECISION]='authorise|deny|none'
  [AUTH_DELAY_S]="$NUMBER"       [AUTH_TTL_S]="$NUMBER"
  [THREAT_TIMEOUT]="$NUMBER"     [REACT_S]="$NUMBER"
)

# Only the configuration file sets the scenario: a value left exported in this
# terminal must not leak into the runs.
unset "${!KNOBS[@]}" SEED STAY_UP BAG_DIR MANUAL_AUTH MOVE_THRESHOLD_M

MANIFEST_HEADER="campaign,configuration,run,attempt,seed,commit,host"
MANIFEST_HEADER+=",started_utc,duration_s,exit_code,outcome,valid,folder"

log() { echo "[campaign] $*"; }
die() { log "$*"; exit 1; }

usage() {
  echo "usage: $0 <campaign> [configuration ...]"
  echo "       variables: RUNS, FIRST_SEED, MAX_HOURS, MAX_ATTEMPTS, HEADLESS"
  echo "       configurations: $CONFIG_FILE"
}

# --- arguments -------------------------------------------------------------------
[ $# -ge 1 ] || { usage; exit 1; }
CAMPAIGN="$1"
shift
[[ "$CAMPAIGN" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
  || die "campaign name '$CAMPAIGN': use letters, digits, '.', '_' and '-'."
for v in RUNS FIRST_SEED MAX_ATTEMPTS; do
  [[ "${!v}" =~ ^[1-9][0-9]*$ ]] || die "$v must be a positive integer, got '${!v}'."
done
if [ -n "$MAX_HOURS" ] && ! [[ "$MAX_HOURS" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  die "MAX_HOURS must be a number of hours, got '$MAX_HOURS'."
fi

# --- configurations --------------------------------------------------------------
declare -A CONF_VARS=()
ALL_CONFS=()
lineno=0
while IFS= read -r line || [ -n "$line" ]; do
  lineno=$((lineno + 1))
  line="${line%%#*}"
  read -r name rest <<< "$line"
  [ -z "$name" ] && continue
  where="$CONFIG_FILE:$lineno"
  [[ "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "$where: bad configuration name '$name'."
  [ -z "${CONF_VARS[$name]+set}" ] || die "$where: '$name' is defined twice."
  read -ra tokens <<< "$rest"
  for tok in "${tokens[@]}"; do
    [[ "$tok" =~ ^([A-Z_]+)=(.*)$ ]] || die "$where: '$tok' is not VARIABLE=value."
    var="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    [ -n "${KNOBS[$var]+set}" ] \
      || die "$where: '$var' is not a scenario variable of test_pipeline.sh."
    [[ "$value" =~ ^(${KNOBS[$var]})$ ]] \
      || die "$where: '$value' is not a valid value of $var."
  done
  CONF_VARS[$name]="$rest"
  ALL_CONFS+=("$name")
done < "$CONFIG_FILE"
[ "${#ALL_CONFS[@]}" -gt 0 ] || die "$CONFIG_FILE defines no configuration."

if [ $# -gt 0 ]; then
  SELECTED=()
  for c in "$@"; do
    [ -n "${CONF_VARS[$c]+set}" ] || die "unknown configuration '$c' (see $CONFIG_FILE)."
    SELECTED+=("$c")
  done
else
  SELECTED=("${ALL_CONFS[@]}")
fi

# --- code, campaign folder, manifest ---------------------------------------------
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  log "the working tree has uncommitted changes:"
  git status --short --untracked-files=no | sed 's/^/[campaign]   /'
  die "commit them first: the manifest must name the code that produced the bags."
fi
COMMIT=$(git rev-parse --short=12 HEAD)
HOST=$(hostname)

CAMPAIGN_DIR="$CAMPAIGNS_DIR/$CAMPAIGN"
MANIFEST="$CAMPAIGN_DIR/manifest.csv"
ENV_FILE="$CAMPAIGN_DIR/campaign.env"
mkdir -p "$CAMPAIGN_DIR"

# One session per campaign at a time. The lock lives as long as file
# descriptor 9 is open, so the steps of a run are started with 9>&-: a process
# they leave behind must not hold the lock after the session.
exec 9> "$CAMPAIGN_DIR/.lock"
flock -n 9 || die "campaign '$CAMPAIGN' is already running in another terminal."

if [ -f "$ENV_FILE" ]; then
  first_seed=$(sed -n 's/^FIRST_SEED=//p' "$ENV_FILE")
  first_commit=$(sed -n 's/^COMMIT=//p' "$ENV_FILE")
  [ "$first_seed" = "$FIRST_SEED" ] \
    || die "this campaign uses FIRST_SEED=$first_seed: its seeds cannot change."
  if [ "$first_commit" != "$COMMIT" ] && [ "${ALLOW_NEW_COMMIT:-0}" != "1" ]; then
    log "this campaign started at commit $first_commit; the code is now at $COMMIT."
    die "finish it at $first_commit, start a new campaign, or set ALLOW_NEW_COMMIT=1."
  fi
else
  {
    echo "FIRST_SEED=$FIRST_SEED"
    echo "SEED_STEP=$SEED_STEP"
    echo "COMMIT=$COMMIT"
    echo "STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$ENV_FILE"
fi
if [ -f "$MANIFEST" ]; then
  [ "$(head -1 "$MANIFEST")" = "$MANIFEST_HEADER" ] \
    || die "$MANIFEST does not start with the expected header."
else
  echo "$MANIFEST_HEADER" > "$MANIFEST"
fi

# --- the scenario must be down, the disk not full ---------------------------------
running=$({ pgrep -ax px4; pgrep -ax MicroXRCEAgent
            pgrep -af -- "gz sim|gz_sim_serv|ros2 launch guarded_swarms_bringup coastal_pipeline\.launch"
          } 2>/dev/null | grep -v '<defunct>')
if [ -n "$running" ]; then
  log "a scenario is already running (make demo-coastal?):"
  while IFS= read -r line; do log "  $line"; done <<< "$running"
  die "close it, or stop it with ./scripts/sim/coastal_down.sh, then retry."
fi
free_gb=$(df -Pk "$CAMPAIGN_DIR" | awk 'NR == 2 { printf "%d", $4 / 1048576 }')
if [ "${free_gb:-0}" -lt "$MIN_FREE_GB" ]; then
  log "WARNING: only ${free_gb} GB free on the disk of $CAMPAIGN_DIR."
fi

# --- helpers -----------------------------------------------------------------------
# "<valid attempts> <attempts>" of one run, from the manifest.
run_state() {
  awk -F, -v c="$1" -v r="$2" '
    NR > 1 && $2 == c && $3 == r { n++; if ($12 == "yes") v++ }
    END { printf "%d %d\n", v, n }' "$MANIFEST"
}

# Outcome of an attempt from the exit code of record_run.sh. A run without a
# ConfirmedThreat is a valid result: it counts against the completion rate.
outcome_of() {
  case "$1" in
    0) echo completed ;;
    1) echo no-threat ;;
    2) echo refused ;;
    3) echo guard-stop ;;
    130) echo interrupted ;;
    *) echo error ;;
  esac
}

# Valid runs per configuration, the total still to do, and the failed attempts
# of the whole campaign so far. Interrupted attempts are not failures: the run
# was stopped on purpose.
summary() {
  awk -F, -v confs="${SELECTED[*]}" -v runs="$RUNS" '
    NR > 1 {
      if ($12 == "yes") ok[$2 SUBSEP $3] = 1
      else if ($11 != "interrupted") nf++
    }
    END {
      n = split(confs, c, " ")
      tv = 0
      for (i = 1; i <= n; i++) {
        nv = 0
        for (r = 1; r <= runs; r++) if ((c[i] SUBSEP r) in ok) nv++
        tv += nv
        printf "[campaign]   %-16s %3d/%d valid\n", c[i], nv, runs
      }
      printf "[campaign]   total: %d/%d valid, %d to do (failed attempts so far: %d)\n", \
             tv, n * runs, n * runs - tv, nf
    }' "$MANIFEST"
}

# True once the session has lasted MAX_HOURS.
time_is_up() {
  [ -n "$MAX_HOURS" ] && LC_ALL=C awk -v s=$((SECONDS - SESSION_START)) \
    -v h="$MAX_HOURS" 'BEGIN { exit !(s >= h * 3600) }'
}

# One attempt of run <run> of <configuration>, appended to the manifest. Sets
# LAST_OUTCOME, LAST_FOLDER, and TEARDOWN_OK (1 if the scenario stopped
# cleanly) for the session loop.
attempt_run() {
  local conf="$1" run="$2" seed="$3" attempt="$4"
  local base folder started t0 elapsed rc outcome valid tokens=()
  base="$CAMPAIGN_DIR/$conf/$(printf 'run-%02d-seed%d' "$run" "$seed")"
  folder="$base"
  [ "$attempt" -gt 1 ] && folder="$base-try$attempt"
  # Never overwrite: a folder without its manifest line stays as it is.
  while [ -e "$folder" ]; do
    attempt=$((attempt + 1))
    folder="$base-try$attempt"
  done
  mkdir -p "$folder/logs"
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  t0=$SECONDS
  # Only the logs of this attempt are copied next to its bag.
  rm -f /tmp/gs_*.log "$SIM_LOG_DIR"/*.log

  log "$conf, run $run/$RUNS, seed $seed, attempt $attempt: starting the scenario..."
  "$COASTAL_UP" > "$folder/logs/coastal_up.log" 2>&1 9>&-
  rc=$?
  if [ "$INTERRUPTED" = 1 ]; then
    outcome=interrupted
  elif [ "$rc" -ne 0 ]; then
    outcome=sim-failed
  else
    log "$conf, run $run/$RUNS: scenario ready, recording the run..."
    read -ra tokens <<< "${CONF_VARS[$conf]}"
    env "${tokens[@]}" SEED="$seed" STAY_UP=0 BAG_DIR="$folder/bag" \
      "$RECORD_RUN" "$CAMPAIGN/$conf/run-$run" > "$folder/logs/record_run.log" 2>&1 9>&-
    rc=$?
    outcome=$(outcome_of "$rc")
    [ "$INTERRUPTED" = 1 ] && outcome=interrupted
  fi

  cp /tmp/gs_*.log "$folder/logs/" 2>/dev/null
  cp "$SIM_LOG_DIR"/*.log "$folder/logs/" 2>/dev/null
  TEARDOWN_OK=1
  if ! "$COASTAL_DOWN" > "$folder/logs/coastal_down.log" 2>&1 9>&-; then
    TEARDOWN_OK=0
    log "WARNING: the scenario did not stop cleanly, see $folder/logs/coastal_down.log"
  fi

  case "$outcome" in
    completed|no-threat) valid=yes ;;
    *) valid=no ;;
  esac
  elapsed=$((SECONDS - t0))
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$CAMPAIGN" "$conf" "$run" \
    "$attempt" "$seed" "$COMMIT" "$HOST" "$started" "$elapsed" "$rc" "$outcome" \
    "$valid" "$folder" >> "$MANIFEST"
  log "$conf, run $run/$RUNS: $outcome (exit $rc) in $((elapsed / 60)) min $((elapsed % 60)) s"
  LAST_OUTCOME="$outcome"
  LAST_FOLDER="$folder"
}

# --- the session -------------------------------------------------------------------
INTERRUPTED=0
# Ctrl-C reaches the run in progress, which closes itself; the session ends
# after it. The scenario runs detached and is stopped by coastal_down.sh.
trap 'INTERRUPTED=1' INT TERM HUP
SESSION_START=$SECONDS

log "campaign '$CAMPAIGN': ${#SELECTED[@]} configuration(s) x $RUNS runs, commit $COMMIT"
[ -n "$MAX_HOURS" ] && log "this session ends after $MAX_HOURS h"
summary

stop_reason=""
PUT_ASIDE=()       # runs that failed MAX_ATTEMPTS times in this session
aside_in_a_row=0   # runs put aside one after the other
for run in $(seq 1 "$RUNS"); do
  seed=$((FIRST_SEED + SEED_STEP * (run - 1)))
  for conf in "${SELECTED[@]}"; do
    failures=0     # failed attempts of this run in a row, in this session
    while :; do
      if [ "$INTERRUPTED" = 1 ]; then stop_reason="interrupted"; break 3; fi
      read -r valid attempts <<< "$(run_state "$conf" "$run")"
      [ "$valid" -gt 0 ] && break
      if [ "$failures" -ge "$MAX_ATTEMPTS" ]; then
        log "$conf run $run failed $MAX_ATTEMPTS times: put aside until the next session."
        PUT_ASIDE+=("$conf run $run")
        aside_in_a_row=$((aside_in_a_row + 1))
        [ "$aside_in_a_row" -ge 2 ] && { stop_reason="set-up"; break 3; }
        break
      fi
      if time_is_up; then stop_reason="time-limit"; break 3; fi
      attempt_run "$conf" "$run" "$seed" $((attempts + 1))
      case "$LAST_OUTCOME" in
        completed|no-threat) aside_in_a_row=0 ;;
        interrupted) ;;
        *) failures=$((failures + 1)) ;;
      esac
      if [ "$TEARDOWN_OK" != 1 ]; then stop_reason="teardown"; break 3; fi
    done
  done
done
[ "$INTERRUPTED" = 1 ] && stop_reason="interrupted"

summary
if [ "${#PUT_ASIDE[@]}" -gt 0 ]; then
  printf -v aside '%s, ' "${PUT_ASIDE[@]}"
  log "put aside after $MAX_ATTEMPTS failed attempts each: ${aside%, }."
  log "the logs of each attempt are in its folder; the next session tries them again."
fi
case "$stop_reason" in
  interrupted)
    log "stopped with Ctrl-C. Run the same command to continue."
    exit 130 ;;
  set-up)
    log "STOPPED: two runs in a row failed $MAX_ATTEMPTS times each: the set-up needs a look."
    log "see the logs in $LAST_FOLDER/logs/, fix the cause,"
    log "then run the same command to continue."
    exit 1 ;;
  teardown)
    log "STOPPED: the scenario did not stop cleanly after $conf run $run."
    log "see $LAST_FOLDER/logs/coastal_down.log, stop what is left"
    log "(./scripts/sim/coastal_down.sh), then run the same command to continue."
    exit 1 ;;
  time-limit)
    log "session time of $MAX_HOURS h is up. Run the same command to continue." ;;
  *)
    if [ "${#PUT_ASIDE[@]}" -eq 0 ]; then
      log "nothing left to do in this campaign."
    else
      log "every other run is done. Run the same command to try those again."
    fi ;;
esac
[ "${#PUT_ASIDE[@]}" -eq 0 ] || exit 1
exit 0
