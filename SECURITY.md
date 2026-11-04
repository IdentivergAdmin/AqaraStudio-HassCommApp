# Security policy

## Scope

The `0.1.4b1` integration is a community beta, independent of Aqara.
Physical acceptance is required before relying on its states for important
automations.

**Native light controls are enabled by default only for positively identified
lights with advertised writable traits.** Advanced switches/outlets remain
off until enabled by the owner. There is no remote unlock, garage actuation,
commissioning, unbinding, arbitrary execution, cloud callback, telemetry or
automatic firewall configuration. No separate Supervisor App is necessary.

## Credentials and network access

- Enter tokens only in HA's local config flow. The token is stored in the config
  entry and can therefore be present in private HA storage/backups. Protect both.
- Never commit/post API tokens, authorization headers, onboarding codes,
  `.storage` files, raw private captures, addresses, personal device names or
  detailed household topology.
- HTTP exposes bearer tokens in cleartext on the network. Use HTTPS with a
  trusted certificate where supported and limit network access to the hub.
  Request only the API permission scope that your Studio deployment requires.
- HTTPS verification is not disabled. Do not solve certificate problems with a
  universal TLS bypass.
- If a token is exposed, revoke/rotate it in Studio and reauthenticate locally in
  HA. Do not put the replacement token in a support issue.

## Logs and diagnostics

The integration avoids logging authorization headers or whole household
payloads. Diagnostics export selected metadata and redact sensitive identifiers
and connection details. Vendor content is data and is never executed.

Review every attachment before sharing. HA-wide debug logs and third-party
integrations are outside this integration's redaction boundary. Useful reports
include versions, model codes, exact function/trait and a sanitized reproduction.

## Report a vulnerability

Use **Security → Report a vulnerability** if GitHub private reporting is enabled
for this repository. If that option is unavailable, open a public issue asking
for a private reporting channel **without exploit details, credentials,
device/network identifiers or raw data**. A maintainer can provide an appropriate
private channel. Do not assume a nonexistent private channel or send secrets to
an unverified contact.

Include affected versions, impact, required access and a minimal sanitized
reproduction in the private report. No response-time or disclosure SLA is
promised by this volunteer community project.
