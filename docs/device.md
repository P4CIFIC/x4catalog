# Connecting an X4

The XTEINK X4 speaks HTTP and WebSocket through CrossPoint on your local network. Files never go through x4catalog.com to reach the device.

## From x4catalog.com (Chrome)

The public site is HTTPS. CrossPoint is HTTP (`http://crosspoint.local` and `ws://…:81`). Supporting browsers can ask for **local network access** and then talk to the device directly.

1. Put the X4 and this computer on the same LAN.
2. Open [x4catalog.com/device](https://x4catalog.com/device) or send from Browse.
3. Enter `crosspoint.local` or the device IP.
4. Allow local network access if the browser prompts.
5. If `.local` fails, use the IPv4 address from the CrossPoint screen.

This uses `fetch(..., { targetAddressSpace: 'local' })`. Safari and Firefox may still block it. Uploads also need the CrossPoint WebSocket; if that is blocked after HTTP works, use the local catalog.

## Local catalog (always works)

1. Put the X4 and your computer on the same LAN.
2. Run `uv run x4catalog serve`.
3. Open <http://127.0.0.1:8765>.
4. Enter the CrossPoint address (`crosspoint.local` or the device IP).
5. Select images and send them to `/.sleep`, or manage books on the Device page.

CrossPoint 1.5 allows the browser to talk to the device directly (CORS). Older firmware falls back to the catalog's loopback proxy. The hosted site has no proxy.

## Addresses

- Default hostname: `crosspoint.local`
- Sleep screens: `/.sleep`
- Books: visible folders only (EPUB, XTC, XTCH, TXT)
