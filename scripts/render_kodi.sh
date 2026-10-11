#!/usr/bin/env bash
# Start the Flathub Kodi build under Xvfb with skin.bingie and capture screenshots and kodi.log.
# Used by .github/workflows/render.yml; needs flatpak + tv.kodi.Kodi, Xvfb, ImageMagick and python3.
#
#   OUT=<artifact dir> KODI_DATA=<special://home> scripts/render_kodi.sh <skin zip>
#
# Kodi runs twice. Phase 1 (default Estuary skin) registers the add-ons copied into the profile and
# enables them over JSON-RPC, because Kodi disables add-ons it finds on disk. Phase 2 selects
# skin.bingie in guisettings.xml before start-up, so no "Keep this skin?" dialog appears, waits for
# Home, and screenshots Home and a few windows. Exit status: 0 = rendered, 1 = Kodi ran but Bingie
# or Home did not load. kodi.log is checked separately (kodi_render.py check-log).
set -euo pipefail

ZIP=${1:?skin zip}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:?artifact directory}
KODI_DATA=${KODI_DATA:-$HOME/.var/app/tv.kodi.Kodi/data}   # XDG_DATA_HOME inside the Flathub sandbox
APP=${KODI_FLATPAK:-tv.kodi.Kodi}
export DISPLAY=${DISPLAY:-:99}
HELPER=(python3 "$ROOT/scripts/kodi_render.py")
KODI_PID=

log() { echo "[render $(date +%H:%M:%S)] $*"; }

start_xvfb() {
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then return; fi
  Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp +extension GLX >"$OUT/xvfb.log" 2>&1 &
  for _ in $(seq 30); do xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && return; sleep 1; done
  log "Xvfb did not start"; exit 1
}

start_kodi() {  # $1 = phase name; Kodi's own stdout/stderr go to the artifact
  local runner=()
  command -v dbus-run-session >/dev/null && runner=(dbus-run-session --)
  "${runner[@]}" flatpak run --user --env=LIBGL_ALWAYS_SOFTWARE=1 --env=DISPLAY="$DISPLAY" \
    "$APP" --windowing=x11 >"$OUT/$1-stdout.log" 2>&1 &
  KODI_PID=$!
  log "$1: Kodi started (pid $KODI_PID)"
}

stop_kodi() {  # $1 = phase name; polite quit, then kill, then keep its log
  "${HELPER[@]}" rpc quit || true
  for _ in $(seq 60); do kill -0 "$KODI_PID" 2>/dev/null || break; sleep 1; done
  if kill -0 "$KODI_PID" 2>/dev/null; then
    log "$1: Kodi did not quit; killing it"
    flatpak kill "$APP" 2>/dev/null || kill "$KODI_PID" 2>/dev/null || true
    sleep 3
  fi
  wait "$KODI_PID" 2>/dev/null || true
  cp "$KODI_DATA/temp/kodi.log" "$OUT/$1-kodi.log" 2>/dev/null || log "$1: no kodi.log in $KODI_DATA/temp"
}

shot() {  # $1 = file name without extension
  sleep "${SETTLE:-6}"
  if ! import -display "$DISPLAY" -window root "$OUT/$1.png" 2>/dev/null; then
    xwd -root -display "$DISPLAY" -silent | convert xwd:- "png:$OUT/$1.png"
  fi
  log "screenshot $1.png"
}

mkdir -p "$OUT" "$KODI_DATA/addons"
start_xvfb
trap 'kill -0 "${KODI_PID:-0}" 2>/dev/null && flatpak kill "$APP" 2>/dev/null; true' EXIT

# Profile: the built skin, its dependencies (official repository or stubs) and minimal settings.
rm -rf "$KODI_DATA/addons/skin.bingie"
python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$ZIP" "$KODI_DATA/addons"
"${HELPER[@]}" deps --dest "$KODI_DATA/addons" --manifest "$OUT/dependencies.json"
"${HELPER[@]}" profile --data "$KODI_DATA"
mapfile -t ADDONS < <(python3 -c 'import json, sys; print("\n".join(json.load(open(sys.argv[1]))))' "$OUT/dependencies.json")

# Phase 1: register and enable the add-ons under the default skin.
start_kodi phase1
"${HELPER[@]}" rpc wait --timeout 240 || { stop_kodi phase1; log "Kodi never answered JSON-RPC"; exit 1; }
"${HELPER[@]}" rpc enable "${ADDONS[@]}" skin.bingie || log "some add-ons could not be enabled (see above)"
shot phase1-default-skin
stop_kodi phase1

# Phase 2: start straight into Bingie.
"${HELPER[@]}" set-skin --data "$KODI_DATA" --skin skin.bingie
start_kodi phase2
status=0
"${HELPER[@]}" rpc wait --timeout 240 || status=1
if [ "$status" = 0 ] && "${HELPER[@]}" rpc skin skin.bingie; then
  # Skin Shortcuts may rebuild the menu and reload the skin once after the first Home load.
  "${HELPER[@]}" rpc wait-window 10000 --timeout 240 || status=1
  SETTLE=30 shot 01-home
  "${HELPER[@]}" rpc window skinsettings && shot 02-skin-settings || true
  "${HELPER[@]}" rpc builtin 'ActivateWindow(1171)' && shot 03-experience-options || true
  "${HELPER[@]}" rpc window home && "${HELPER[@]}" rpc window videos 'videodb://movies/titles/' \
    && SETTLE=10 shot 04-movies || true
  "${HELPER[@]}" rpc window settings && shot 05-settings || true
  "${HELPER[@]}" rpc window home && shot 06-home-again || true
else
  status=1
  shot phase2-failed || true
  log "Bingie is not the active skin: a dependency is missing or the skin failed to load (see phase2-kodi.log)"
fi
stop_kodi phase2
exit "$status"
