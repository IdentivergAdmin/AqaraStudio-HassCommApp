#!/usr/bin/env bash
set -Eeuo pipefail

# Overrides are used only by the local test harness. Supervisor uses defaults.
source_dir="${PAYLOAD_DIR:-/opt/aqara_studio}"
config_dir="${HA_CONFIG_DIR:-/homeassistant}"
options_file="${APP_OPTIONS_PATH:-/data/options.json}"
parent_dir="${config_dir}/custom_components"
target_dir="${parent_dir}/aqara_studio"

log() { printf '[Aqara Studio Installer] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

[[ -d "$source_dir" && -f "$source_dir/manifest.json" && -f "$source_dir/__init__.py" && -f "$source_dir/config_flow.py" ]] || fail "Packaged integration is incomplete. No files changed."
[[ -d "$config_dir" && -w "$config_dir" ]] || fail "Home Assistant configuration is not mounted read-write. No files changed."
[[ -f "$options_file" ]] || fail "App options are missing. No files changed."
command -v jq >/dev/null || fail "Missing jq in installer image. No files changed."

replace_existing="$(jq -er '.replace_existing | if type == "boolean" then tostring else error("replace_existing must be boolean") end' "$options_file")" || fail "Invalid installer option. No files changed."
version="$(jq -er '.version | strings' "$source_dir/manifest.json")" || fail "Invalid integration manifest. No files changed."

[[ ! -L "$parent_dir" ]] || fail "custom_components is a symlink; refusing to modify it."
[[ ! -L "$target_dir" ]] || fail "Existing aqara_studio is a symlink; refusing to replace it."
[[ ! -e "$target_dir" || -d "$target_dir" ]] || fail "Existing aqara_studio is not a directory; refusing to replace it."

mkdir -p -- "$parent_dir"

if [[ -d "$target_dir" && "$replace_existing" != "true" ]]; then
  log "Aqara Studio already exists at $target_dir; leaving it unchanged."
  log "For an upgrade, set replace_existing=true in this app's Configuration tab, then run once again."
  exit 0
fi

stage_dir="${parent_dir}/.aqara_studio_stage_$$"
[[ ! -e "$stage_dir" && ! -L "$stage_dir" ]] || fail "Temporary staging path already exists."
cleanup() { if [[ -d "$stage_dir" ]]; then rm -rf -- "$stage_dir"; fi; }
trap cleanup EXIT

cp -a -- "$source_dir" "$stage_dir" || fail "Could not stage integration; existing installation unchanged."
[[ -f "$stage_dir/manifest.json" && -f "$stage_dir/__init__.py" ]] || fail "Staged integration failed validation."

backup_dir=""
if [[ -d "$target_dir" ]]; then
  backup_root="${config_dir}/aqara_studio_installer_backups"
  mkdir -p -- "$backup_root" || fail "Cannot create backup directory. Existing integration unchanged."
  backup_dir="${backup_root}/aqara_studio_$(date -u +%Y%m%dT%H%M%SZ)_$$"
  mv -- "$target_dir" "$backup_dir" || fail "Could not back up existing integration. No files replaced."
  log "Previous integration moved to: $backup_dir"
fi

if ! mv -- "$stage_dir" "$target_dir"; then
  if [[ -n "$backup_dir" && -d "$backup_dir" ]]; then
    mv -- "$backup_dir" "$target_dir" || log "CRITICAL: Restore manually from $backup_dir"
  fi
  fail "Could not activate staged integration."
fi

log "Installed native Aqara Studio integration version ${version}."
log "Restart Home Assistant Core, then go to Settings > Devices & services > Add integration > Aqara Studio."
log "Keep the working REST sensors in place until physical state and availability checks pass."
log "This is a one-shot installer; the app stopping after success is expected."
