# Verification record

## Automated

19 passing tests across booking logic, HTTP integration and the WSGI adapter. JavaScript syntax checks pass for `public/app.js` and `public/staff.js`.

- Six concurrent requests for a capacity-one slot: exactly one accepted, five rejected.
- Pending appointments reserve capacity; overlapping windows reject when full; adjacent windows remain valid.
- Branch isolation and configurable capacity tested.
- Full-day and interval blocks, opening/closing boundaries, estimated duration, lead time, invalid slots and missing configuration tested.
- Identical submission retry returns the same reference. Token reuse with changed data and duplicate requests using new tokens are rejected.
- Staff API denies unauthenticated reads/writes, requires CSRF for mutations and invalidates logged-out sessions.
- Staff confirm, reschedule, conflict rejection, cancel, complete and closed-state protection tested.
- Configuration cannot invalidate active reservations.
- Contact form saves a retrievable staff enquiry.
- Public page routes, car asset, logo sheet and favicon return HTTP 200.
- WSGI adapter serves configuration and HTML and rejects unsupported methods.

## Browser

- Desktop homepage inspected at 1440 × 1000; mobile at 390 × 844. No horizontal overflow or unloaded imagery.
- Desktop and mobile screenshots saved in `qa/`.
- Mobile navigation opens and exposes the expected page links.
- Static motion toggle verified; computed animation is `none`. Reduced-motion CSS and data-saver fallback are implemented; a throttled-device performance benchmark was not performed.
- Full mobile branch → service → vehicle → time → details → review → submit flow completed against an isolated QA database; success explicitly says awaiting staff confirmation and shows a unique reference.
- Staff login displays that request; confirming changes its status and explicitly says no notification was sent.
- Structured staff configuration saved successfully; mobile header overflow was found and fixed, then verified at 390px.
- Staff logout returns to the login screen.
- Real preview keeps booking disabled until verified business configuration exists; this was checked in the browser.
- Phone, WhatsApp and map links remain absent until real details are supplied; their real destinations cannot be verified without those details.

## Assets

All 11 PNG logo exports have RGBA transparency. The three concepts use original outlined SVG letterforms. Desktop hero WebP: 153,346 bytes; smaller hero WebP: 38,006 bytes. Download kit contains relative-path concept sheet plus all assets.

## Limits

No verified branch photos, before/after work, map pins, contacts, hours, prices, package offers, service duration/capacity or social accounts were supplied. Empty gallery and package areas contain explicit availability/enquiry copy, not fabricated evidence. No public deployment, live notification delivery, real staff account creation or production reverse-proxy setup was performed. The separate QA fixture and its fabricated settings were not copied to the real database.

## Customer status follow-up

20 tests now pass. The added HTTP test verifies private-link access, identical link on submission retry, rejection of reference-only and incorrect-token requests, exclusion of contact details, confirmed/rescheduled/cancelled updates and noindex headers. The existing demo booking status page was visually verified without changing its appointment status. Screenshot: `qa/booking-status.jpg`.
