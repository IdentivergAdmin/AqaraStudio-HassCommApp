#!/usr/bin/env bash
set -Eeuo pipefail

# The Home Assistant Supervisor mounts /homeassistant read-write. Overrides are
# limited to isolated filesystem tests; no Supervisor token or API access needed.
source_dir="${PAYLOAD_DIR:-/opt/aqara_studio}"
config_dir="${HA_CONFIG_DIR:-/homeassistant}"
parent_dir="${config_dir}/custom_components"
target_dir="${parent_dir}/aqara_studio"
backup_root="${config_dir}/aqara_studio_installer_backups"

log() { printf '[Aqara Studio] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

manifest_version() {
  local file="$1"
  [[ -f "$file" && ! -L "$file" ]] || return 1
  jq -e '.domain == "aqara_studio"' "$file" >/dev/null || return 1
  jq -er '.version | select(type == "string" and length > 0)' "$file" || return 1
}

# Compare the PEP 440 version subset used by this integration:
# X.Y.Z, X.Y.ZaN, X.Y.ZbN and X.Y.ZrcN. Unknown forms fail closed.
# Echo -1 if left is older, 0 if equal, or 1 if newer.
version_tuple() {
  local version="$1" stage=4 serial=0
  local pattern='^([0-9]{1,8})\.([0-9]{1,8})\.([0-9]{1,8})(a([0-9]{1,8})|b([0-9]{1,8})|rc([0-9]{1,8}))?$'
  [[ "$version" =~ $pattern ]] || return 1
  local major="${BASH_REMATCH[1]}" minor="${BASH_REMATCH[2]}" patch="${BASH_REMATCH[3]}"
  if [[ -n "${BASH_REMATCH[5]:-}" ]]; then
    stage=1; serial="${BASH_REMATCH[5]}"
  elif [[ -n "${BASH_REMATCH[6]:-}" ]]; then
    stage=2; serial="${BASH_REMATCH[6]}"
  elif [[ -n "${BASH_REMATCH[7]:-}" ]]; then
    stage=3; serial="${BASH_REMATCH[7]}"
  fi
  printf '%d %d %d %d %d\n' "$((10#$major))" "$((10#$minor))" "$((10#$patch))" "$stage" "$((10#$serial))"
}

compare_versions() {
  local left="$1" right="$2" a b index
  a="$(version_tuple "$left")" || return 2
  b="$(version_tuple "$right")" || return 2
  local -a av bv
  read -r -a av <<< "$a"
  read -r -a bv <<< "$b"
  for index in 0 1 2 3 4; do
    if (( av[index] < bv[index] )); then printf '%s\n' -1; return 0; fi
    if (( av[index] > bv[index] )); then printf '%s\n' 1; return 0; fi
  done
  printf '%s\n' 0
}

[[ -d "$source_dir" && ! -L "$source_dir" ]] || fail 'Bundled integration directory is missing; nothing changed.'
[[ -f "$source_dir/__init__.py" && -f "$source_dir/config_flow.py" ]] || fail 'Bundled integration is incomplete; nothing changed.'
[[ -d "$config_dir" && -w "$config_dir" ]] || fail 'Home Assistant configuration mount is not writeable; nothing changed.'
command -v jq >/dev/null || fail 'Missing required JSON parser; nothing changed.'

new_version="$(manifest_version "$source_dir/manifest.json")" || fail 'Bundled manifest is invalid; nothing changed.'
version_tuple "$new_version" >/dev/null || fail 'Bundled version is unsupported; nothing changed.'

[[ ! -L "$parent_dir" ]] || fail 'custom_components is a symlink; refusing changes.'
[[ ! -L "$target_dir" ]] || fail 'The installed integration is a symlink; refusing changes.'
[[ ! -e "$target_dir" || -d "$target_dir" ]] || fail 'The installed integration is not a folder; refusing changes.'
[[ ! -L "$backup_root" ]] || fail 'The backup root is a symlink; refusing changes.'

current_version=''
if [[ -d "$target_dir" ]]; then
  current_version="$(manifest_version "$target_dir/manifest.json")" || fail 'Existing integration manifest is missing/invalid. No replacement performed; repair it manually.'
  comparison="$(compare_versions "$current_version" "$new_version")" || fail 'Cannot compare existing and bundled versions; nothing changed.'
  if [[ "$comparison" == 0 ]]; then
    log "ALREADY CURRENT — Aqara Studio ${current_version}. No changes; no restart needed."
    exit 0
  fi
  if [[ "$comparison" == 1 ]]; then
    fail "DOWNGRADE BLOCKED — installed ${current_version}, bundled ${new_version}. Update the Installer App first. Nothing changed."
  fi
  log "UPGRADE ${current_version} -> ${new_version} (automatic backup)."
else
  log "FIRST INSTALL ${new_version}."
fi

# Stage the complete copy next to the destination so the final rename is atomic.
mkdir -p -- "$parent_dir" || fail 'Cannot create custom_components; no files changed.'
stage_dir="$(mktemp -d "${parent_dir}/.aqara_studio_stage.XXXXXXXX")" || fail 'Cannot create staging folder; no files changed.'
cleanup() {
  if [[ -n "${stage_dir:-}" && -d "$stage_dir" ]]; then rm -rf -- "$stage_dir"; fi
}
trap cleanup EXIT

cp -a -- "$source_dir/." "$stage_dir/" || fail 'Could not stage integration; existing installation unchanged.'
for name in manifest.json __init__.py config_flow.py; do
  [[ -f "$stage_dir/$name" && ! -L "$stage_dir/$name" ]] || fail 'Staged integration is incomplete; existing installation unchanged.'
  cmp -s -- "$source_dir/$name" "$stage_dir/$name" || fail 'Staged copy verification failed; existing installation unchanged.'
done

backup_dir=''
if [[ -d "$target_dir" ]]; then
  mkdir -p -- "$backup_root" || fail 'Cannot create backup folder; existing installation unchanged.'
  backup_dir="$(mktemp -d "${backup_root}/aqara_studio_${current_version}_$(date -u +%Y%m%dT%H%M%SZ).XXXXXXXX")" || fail 'Cannot reserve backup folder; existing installation unchanged.'
  rmdir -- "$backup_dir" || fail 'Cannot reserve a unique backup path; existing installation unchanged.'
  mv -- "$target_dir" "$backup_dir" || fail 'Cannot back up existing integration; no files replaced.'
fi

if ! mv -- "$stage_dir" "$target_dir"; then
  if [[ -n "$backup_dir" && -d "$backup_dir" ]]; then
    mv -- "$backup_dir" "$target_dir" || log "CRITICAL: Restore from ${backup_dir} manually."
  fi
  fail 'Cannot activate integration; automatic rollback attempted.'
fi
stage_dir=''

if [[ -n "$backup_dir" ]]; then log "BACKUP: ${backup_dir}"; fi
log "SUCCESS — native integration ${new_version} installed. Restart Home Assistant Core to load the new code."
log 'Existing integration configuration and REST/Matter entities were not changed. The installer now stops normally.'
