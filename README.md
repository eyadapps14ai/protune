# Protune Auto Services

A responsive public website and an authenticated staff workspace. The original project directory was empty; no existing system was replaced.

## Current preview

Demo booking is now enabled for both branches with explicitly fictional 09:00–20:00 hours, capacity 2, and sample service prices/durations. All pages display a demo banner. These are not verified business facts or real appointments. The original unconfigured defaults remain in `config.json`; current sample settings are also recorded in `config.preview.json`.

Local staff access is in `data/PREVIEW_ACCESS.md` (private, not web-accessible). Change settings through `/staff` → Configuration. A database snapshot from before enabling demo mode is in `data/before-demo.sqlite3`. Demo bookings use `DEMO-` references so they remain recognisable later. Remove demo reservations and the preview account before launching; replace sample data with verified values and set `previewMode` to false in Advanced configuration.

## Run locally

Requires Python 3.9+ with timezone data; no third-party application dependencies.

```sh
python3 server.py --port 8080
```

Open http://127.0.0.1:8080. Use an installed Python 3.9+ runtime with timezone data.

## Create your staff account

```sh
python3 server.py --create-staff YOUR_USERNAME
```

The password is entered privately at the terminal, requires at least 12 characters, and is stored as a salted scrypt hash. No default staff account or production password exists. Sign in at `/staff`. Repeat the command to reset an account password. Sessions expire after eight hours and on server restart.

## Business configuration

`config.json` seeds the database only on first startup. Once started, edit the authoritative configuration through Staff → Configuration. This includes addresses, verified map links, phone, WhatsApp, images, hours, capacity, service/category availability, price, duration and blocked dates/intervals. Advanced JSON supports packages, gallery pairs and social links.

Only the business name, branch communities and five requested service types were supplied. Prices, durations, hours, capacity, contact numbers, specific addresses, photos, package offers and social links are intentionally not invented. Online booking starts disabled. Missing prices show “Request a quote”. The vehicle categories are configurable choices, not claims of branch availability. No fabricated customer testimonials or result photographs are included.

To activate booking, set verified hours and capacity, enable relevant service/category options with durations, and enable booking for each branch. Configure closed weekdays by leaving them unticked. Hours use Dubai time and currently support one same-day interval per day; use blocked intervals for lunch breaks. Pending and confirmed appointments both reserve capacity. Cancelled and completed appointments do not. No auto-expiry of pending requests: staff must review and cancel stale ones.

Gallery entries use `{ "title": "Verified job description", "before": "/assets/before.webp", "after": "/assets/after.webp" }`. Only publish photographs you own or have permission to use. Branch imagery is similarly configured. No guessed map locations or phone links are shown.

## Booking integrity and security

SQLite durable storage at `data/protune.sqlite3`, WAL mode, parameterised queries, transactional `BEGIN IMMEDIATE` availability checks, interval-based capacity enforcement, duplicate checks, and idempotent submission keys. The API validates branch, vehicle, service, opening hours, lead time, date horizon, duration, blocks and customer details again at submission. Rescheduling rechecks availability and configuration changes cannot invalidate outstanding bookings. Changes are all-or-nothing.

Staff API access requires an HttpOnly SameSite=Strict session cookie. Mutations require a CSRF token and same-origin request checks. Login/public submission rates are limited per process/IP. Staff data is never included in the public configuration. All staff accounts currently have the same administrative permissions; this is a single-server deployment, not a multi-tenant system.

## Customer booking status

Each new booking returns a private `/booking-status#...` link. Customers should save it from the receipt screen. It displays pending, confirmed, cancelled or completed status, current appointment time, and a rescheduled notice when the time changes. It refreshes every 30 seconds while visible, with manual refresh and copy controls. Staff booking records include the same customer link, including for older bookings.

The 256-bit random access secret is separate from the booking reference and submission token. Reference-only lookups are not allowed. Status responses omit customer names, mobile numbers, email and notes. Status pages are marked noindex and responses are not cached. Anyone with the private link can see appointment details; customers and staff should keep it private. The link does not expire automatically.

## Notifications and contact

Contact submissions are saved to the staff enquiry inbox. No email, SMS, WhatsApp or push notification integration has been configured. Status messages disclose this. A pending booking is never presented as confirmed. Staff must contact customers directly after confirming or rescheduling. No payment is collected.

## Media and logos

- `/logo-concepts.html`: three original vector-native concepts and downloads.
- `public/logos/`: horizontal, compact, gold/light and black SVGs with transparent PNG exports, and brand guidelines.
- Selected concept: Precision Monogram (concept 1).
- Hero: original AI-generated fictional graphite coupe, compressed to WebP (desktop and smaller source). CSS translates it into the dark studio scene once. Headlights, gold lighting and floor reflections are in the image. This is a 2D image motion treatment, not a 3D simulation or video. No third-party stock asset or automaker badge is used. See `ASSETS.md` for generation provenance.
- Reduced-motion preference, data-saver preference and a visible motion toggle provide a static treatment.

## Verification

```sh
python3 -m unittest discover -s tests -v
```

20 tests cover concurrency, capacity, overlaps, adjacent slots, duplicate submission keys, duplicate appointment details, blocked dates/intervals, hours, duration, lead time, branch isolation, invalid customer details, closed booking, staff authentication/CSRF/logout, confirmation/rescheduling/cancellation/completion, protecting existing bookings during configuration, enquiry persistence and public routes.

`python3 tests/preview_fixture.py` starts a disposable QA database at port 8081 with clearly labelled fictional availability. It never changes the actual database. The test-only credentials in that script are not production accounts. Stop it after testing.

Desktop and 390px mobile layouts were inspected in the browser. Full mobile booking and authenticated staff confirmation/configuration were exercised against the disposable fixture. See `QA.md` for results.

## Before public launch

1. Provide verified branch addresses and map pins, hours, phone/WhatsApp, capacity, service/category durations and pricing, confirmed packages, branch/job photographs and social URLs.
2. Create real staff accounts, confirm customer confirmation workflow, set privacy contact and record-retention policy, and configure any desired messaging provider.
3. Choose hosting/domain. This delivery is a local working preview, not a public deployment. The Python/SQLite backend needs a persistent server; it must not be published as a static-only site. Put it behind an HTTPS reverse proxy with request limits and process supervision. Set `PROTUNE_SECURE_COOKIE=1` in HTTPS production. The bundled HTTP server is intended for local preview. `wsgi.py` provides the deployment adapter; run it with a production WSGI server behind HTTPS, using one worker and multiple threads because sessions and rate limits are process-local. For example, after installing Gunicorn in your hosting environment: `gunicorn --workers 1 --threads 8 --bind 127.0.0.1:8080 wsgi:application`. Hosting and reverse-proxy deployment have not been exercised here.
4. Back up SQLite using its backup API (including live WAL state), restrict data directory access, establish retention/deletion procedures, and verify backups restore correctly.
5. Remove development-only empty-gallery copy or upload verified photographs. Add the canonical domain/sitemap and verified branch-address structured data when known. Current JSON-LD only declares the supplied business name, service types and service areas.

No hosting, messaging or payment credentials are embedded in the source.
