# Connecting an X4

Beginner steps live on the site: [x4catalog.com/docs](https://x4catalog.com/docs).
This file is the technical note.

The XTEINK X4 speaks **HTTP** and **WebSocket** through CrossPoint on the
local network. Files go from the browser (or the local catalog) to the
device. They do not go through x4catalog.com.

## Why HTTPS is hard

x4catalog.com is HTTPS. CrossPoint is HTTP:

- REST: `http://crosspoint.local` (or the device IPv4)
- HTTP uploads: `POST /upload?path=/folder` (multipart `file`)
- WebSocket uploads: `ws://crosspoint.local:81/` (or `ws://<ip>:81/`)

A public HTTPS page loading those URLs is mixed content. Browsers block
it unless they implement [Local Network Access](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/local_network_access)
and the user grants permission.

## What the hosted site does

On HTTPS, device `fetch` calls set `targetAddressSpace` to `local` (LAN
host / `.local` / RFC1918) or `loopback` (`127.0.0.1`). Chrome can then
prompt: allow this site to use a device on your network.

There is **no FastAPI proxy** on the hosted site. CrossPoint 1.5 CORS is
required for the browser to talk to the device directly.

On HTTPS, uploads use CrossPoint's HTTP `POST /upload` first (same
`targetAddressSpace` as status). That is the path that survives mixed
content after the user clicks Allow. WebSocket `ws://…:81` is the fast
path on the local HTTP catalog, with HTTP as fallback. CrossPoint's own
file manager does the same. Use 4 KB WebSocket frames; a 1 MB send buffer
overruns the ESP32 on books.

CrossPoint **1.5.0** `/api/status` returns version, IP, RSSI, `freeHeap`
(RAM), uptime, device, and serial. It does **not** report SD free space.
The UI must not block sends on that. Prefer the device IPv4;
`crosspoint.local` is mDNS and often fails in `curl` and some browsers.

Safari and Firefox often have no LNA prompt yet. Guest Wi-Fi and client
isolation also fail.

## Local catalog

`uv run x4catalog serve` binds `127.0.0.1:8765` over HTTP, so mixed
content does not apply.

1. Same LAN as the X4.
2. On the X4 home screen, open **File Transfer** (CrossPoint).
3. Open <http://127.0.0.1:8765>.
4. Enter the address shown there (`crosspoint.local` or the device IP).
5. Send to `/.sleep`, or manage books on Device.

CrossPoint user guide: <https://crosspoint-cloud.idlerecord.com/en>
Firmware source: <https://github.com/crosspoint-reader/crosspoint-reader>

CrossPoint 1.5: browser → device (CORS). Older firmware: browser →
loopback `/api/crosspoint/…` → device.

## Addresses

| What | Value |
| --- | --- |
| Default hostname | `crosspoint.local` (mDNS; often flaky) |
| Sleep screens | `/.sleep` |
| Books | Visible folders only (EPUB, XTC, XTCH, TXT) |
| HTTP upload | `POST /upload?path=/folder`, multipart field `file` |
| WebSocket | port `81`, 4 KB frames, `START:filename:size:destination` |

Prefer the IPv4 from the CrossPoint screen if `.local` does not resolve.

## Security

The public gallery only learns the host string the user typed. It never
receives device files. Do not bind the local catalog off loopback. Do not
relay CrossPoint through a cloud proxy.
