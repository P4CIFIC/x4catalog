# Connecting an X4

The XTEINK X4 speaks HTTP and WebSocket through CrossPoint on your local network. The catalog never reaches the device through the public internet.

## Local catalog (this is the path that works)

1. Put the X4 and your computer on the same LAN.
2. Run `uv run x4catalog serve`.
3. Open <http://127.0.0.1:8765>.
4. Enter the CrossPoint address (`crosspoint.local` or the device IP).
5. Select images and send them to `/.sleep`, or manage books on the Device page.

CrossPoint 1.5 allows the browser to talk to the device directly (CORS). Older firmware falls back to the catalog's loopback proxy.

## Why x4catalog.com cannot send to your X4

The public site is HTTPS. CrossPoint is HTTP (`http://crosspoint.local` and `ws://…:81`). Browsers block that mix. There is no safe way around it from a public HTTPS page.

From the hosted gallery you can:

- Browse and download images
- Run the local catalog and send those files from `127.0.0.1`

The Device page on the public site will not reach hardware. Use it as documentation; do the live work on HTTP localhost.

## Addresses

- Default hostname: `crosspoint.local`
- Sleep screens: `/.sleep`
- Books: visible folders only (EPUB, XTC, XTCH, TXT)
