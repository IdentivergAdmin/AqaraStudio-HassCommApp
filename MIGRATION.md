# Safe migration from existing REST or Matter entities

Install and test Aqara Studio alongside the known-working configuration first.
There is no automatic entity takeover, deletion of another integration's devices,
or editing of Home Assistant registry files.

## 1. Back up and record references

1. Create a full HA backup from **Settings → System → Backups** and store a copy
   somewhere recoverable if HA becomes unavailable.
2. Privately back up the working REST YAML, including its `unique_id`. Protect
   embedded tokens; do not publish the backup.
3. Under **Settings → Devices & services → Entities**, record the exact old entity
   IDs, names, areas and enabled state. Record old internal device IDs used by
   device-based automations.
4. Review automations, scripts, scenes, dashboards, groups and templates for
   those references. Save copies of critical automations before editing.
5. Choose a controlled cutover window. An entity becoming available can trigger
   an automation; temporarily disable relevant physical actions while migrating.

Example record (replace these invented IDs with your own):

| Purpose | Before migration | New Aqara Studio entity |
| --- | --- | --- |
| Test door | `binary_sensor.test_door_rest` | Record the ID HA actually creates |
| Garage contact state | `binary_sensor.garage_contact` | Record the new contact ID |
| Button event | `event.test_button` | Record the new event ID and observed event types |

The garage contact is only a state sensor. No garage actuation is exposed.

## 2. Install alongside existing integrations

Follow [README.md](README.md). Leave the working REST entity enabled. Keep stale
Matter records until their references are understood.

Open new devices under **Devices & services → Aqara Studio** and review their
entities. Confirm contact/leak polarity against the physical device and existing
working sensor before relying on open/closed or wet/dry labels. Unknown is
expected before polarity confirmation.

## 3. Validate equivalent behavior

For every critical contact:

1. Compare Studio, the old entity and the new entity while closed.
2. Open it and compare all three; note latency.
3. Close it and compare again; repeat several cycles.
4. Complete transport interruption/recovery tests in
   [ACCEPTANCE.md](docs/ACCEPTANCE.md). API failure must not produce false-safe
   state.
5. Reload/restart HA and confirm no duplicates or phantom button events.
6. Check other useful readings such as battery, voltage and temperature.

For leaks, use the manufacturer's safe test method and verify both dry and wet
states before enabling alerts. Do not make an experimental event entity the only
trigger for an important action before actual live delivery is validated.

## 4. Release the old entity ID

Disabling an entity alone does **not** free its entity ID for reuse.

1. Temporarily disable critical automations that react to the cutover.
2. If supported, rename the old entity to a temporary ID such as
   `binary_sensor.test_door_legacy`. If HA offers to update references, review
   that choice: the original ID is about to belong to the replacement.
3. For a YAML REST sensor, remove/comment out **only that sensor's stanza**.
   Preserve other sensors sharing the REST resource and all unrelated REST
   integrations. Reload the appropriate integration if supported, or restart.
4. If the old ID remains occupied, remove its unused registry record through the
   HA UI after its provider no longer supplies it. Never edit `.storage`.
5. For obsolete Matter records, remove only the confirmed stale entity/device
   after its dependencies are reviewed. Do not remove working Matter controllers
   or devices as part of this migration.

If HA cannot release an ID safely, keep the new entity's generated ID while
investigating. It can remain installed and tested independently.

## 5. Assign the original ID to the new entity

Open the replacement entity's settings and change **Entity ID** to the exact old
ID. Its integration unique ID remains the new stable Aqara Studio identity; do
not try to replace it with the old REST unique ID.

References using the original entity ID can now resolve to the replacement.
Check templates, groups and dashboards explicitly. The ID swap does not promise
a merge of registry records, device IDs, history or statistics.

## 6. Repair internal device references

A different integration creates a different **device registry ID**. Reusing the
entity ID does not preserve the old `device_id`.

In the automation editor, reselect the new device/entity for device-based
triggers, conditions and actions. Where suitable, use an explicit entity-state
trigger. Contact and event entities have different trigger semantics.

Example contact trigger, **after polarity calibration**:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.garage_contact
    from: "off"
    to: "on"
```

For a door-class HA binary sensor, `on` means open and `off` means closed. The
integration's mapping must be validated before relying on this. The explicit
`from` avoids treating `unavailable` → `on` recovery as this exact transition;
decide deliberately whether your automation should also react when connectivity
recovers while the door is already open. Review your own conditions/actions;
this example does not actuate anything.

Button migration needs a physically observed live event type and a positive
vendor timestamp strictly newer than the cached/reconnect snapshot. Missing/zero
timestamps are diagnostic only and cannot drive automations in this beta. Do not
translate a cached last-event value into a permanent on/off trigger.

## 7. Validate the migration

Re-enable one automation at a time. Trigger it physically and inspect its trace,
conditions and actions. Check notifications and unknown/unavailable behavior.
Repeat after an HA restart and a Studio recovery. Keep the private REST backup
until all critical devices and automations pass. Remove obsolete registry
records through the UI only after confirming no dependencies remain.

## Rollback

1. Disable affected automations and the new Aqara Studio entry/entities.
2. If an original ID was reassigned, rename the new entity to free that ID.
3. Restore only the backed-up REST stanza and its existing unique ID; reload or
   restart HA as appropriate.
4. Restore the expected entity ID in HA's entity settings if needed.
5. Restore recorded automation references, validate the physical sensor, then
   re-enable automations.
6. Leave unrelated REST/Matter integrations untouched. Full HA backup restoration
   is a broader recovery option, not a routine integration rollback step.


## Optional cleanup of permanently removed Studio devices

The integration never deletes registry entries automatically. After a device is
absent from **two complete inventory reconciliations**, Home Assistant's device
page can remove its Aqara Studio registry association through the normal UI.
The Studio identity gateway and currently listed devices cannot be removed this
way. Excluded but still listed devices are also protected. Wait for the normal
inventory cycles, confirm the device was permanently removed in Studio, repair
any automation references, and then use the device page's Delete action.
This only cleans up Home Assistant; it never unbinds or deletes a Studio device.
