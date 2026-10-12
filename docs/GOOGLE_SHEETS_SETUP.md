# Google Sheets setup for Milestone 3B

This setup connects ResearchRadar only to the existing dedicated TEST spreadsheet. Never paste
OAuth client files, access tokens, refresh tokens, or private keys into chat, issues, logs, or the
repository.

## 1. Create or select a Google Cloud project

In Google Cloud Console, create a project for ResearchRadar or select an existing personal
project. Billing is not required for normal Google Sheets API usage.

## 2. Enable the Google Sheets API

Open **APIs & Services > Library**, find **Google Sheets API**, and enable it. Google Drive API is
not required because ResearchRadar opens only the configured spreadsheet ID and does not search
Drive.

## 3. Configure OAuth consent and a Desktop client

In **Google Auth Platform**, configure the consent screen. For an External app in testing mode,
add your own Google account as a test user. Create an OAuth client with application type
**Desktop app** and download its client JSON to a private location outside this repository.

Do not copy the file into the project. Restrict its filesystem permissions to your macOS user.

## 4. Install dependencies and choose authentication

Install the project with the official Google API libraries:

```bash
python -m pip install -e '.[dev,sheets]'
```

Recommended: install Google Cloud CLI and create Application Default Credentials using the
Desktop OAuth client. This opens a browser for authorization:

```bash
gcloud auth application-default login \
  --client-id-file="/private/path/to/desktop-oauth-client.json" \
  --scopes="https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/cloud-platform"
```

Alternative: allow ResearchRadar to start the installed-app browser flow. Point
`GOOGLE_OAUTH_CLIENT_SECRET_FILE` to the private Desktop client file. The first live command opens
the default browser and saves a refresh token with user-only permissions under
`~/.config/research-radar/`, unless `GOOGLE_OAUTH_TOKEN_FILE` overrides that location.

```bash
export GOOGLE_OAUTH_CLIENT_SECRET_FILE="/private/path/to/desktop-oauth-client.json"
```

Use one method. Application Default Credentials are checked first.

## 5. Configure the TEST spreadsheet

Set these variables in the same terminal. The spreadsheet ID is the value between `/d/` and
`/edit` in its URL.

```bash
export GOOGLE_SPREADSHEET_ID="<TEST_SPREADSHEET_ID>"
export RESEARCH_RADAR_SHEETS_ENV="test"
```

Do not add the ID to Python source. The authorized Google account must have Editor access before
an apply command can succeed.

## 6. Run a read-only connection check

```bash
research-radar sheets-status
```

This checks access, approved worksheets, exact headers, and row counts. It writes nothing and
does not print the spreadsheet ID.

## 7. Preview and initialize worksheets

Inspect the initialization plan first:

```bash
research-radar sheets-init --dry-run
```

If it reports incompatible headers, stop and review them manually. ResearchRadar does not repair
or overwrite existing worksheets. After explicit authorization of the first live write, create
only missing worksheets:

```bash
research-radar sheets-init --apply
```

Initialization never deletes worksheets or rows.

## 8. Preview synthetic synchronization

After all seven worksheets exist:

```bash
research-radar sheets-sync --demo --dry-run
```

Review insert, update, unchanged, invalid, and conflict counts. This reads the real spreadsheet
but performs no writes.

## 9. Run the first TEST synchronization

Only after the dry-run is reviewed and explicit authorization is given:

```bash
research-radar sheets-sync --demo --apply
```

All opportunity records are fictional demo data. Production mode refuses demo writes. Run the
dry-run again to confirm idempotence, then edit one `My_Feedback` row and verify that a subsequent
run loads it without changing notes, saved, or hidden values.

## 10. Optional live read-only test

The ordinary test suite is fully mocked. To opt in to the authenticated read-only test:

```bash
RUN_GOOGLE_SHEETS_LIVE_TEST=1 pytest -m live_google_sheets
```

## Troubleshooting

- **No credentials found / browser did not open:** confirm ADC exists, or set the Desktop-client
  path and retry from an interactive terminal.
- **401:** authorization is invalid or expired; recreate ADC or intentionally remove only the
  configured local token and reauthorize.
- **403:** the account lacks access, Sheets API is disabled, or OAuth consent/test-user setup is
  incomplete.
- **404:** verify the environment variable and confirm the account can open that exact sheet.
- **429 or 5xx:** bounded exponential-backoff retries are automatic; wait before another run if
  they are exhausted.
- **Invalid headers:** do not run `--apply`. Compare the first row with `docs/DATA_SCHEMA.md`;
  destructive migration is never automatic.
- **Duplicate Record_ID:** resolve it manually after determining which row contains intended user
  data. The adapter refuses to guess.

Future GitHub Actions authentication will use Workload Identity Federation so no long-lived
service-account key needs to be stored. Deployment remains outside Milestone 3B.

## Dedicated LIVE PILOT setup

LIVE PILOT reuses the existing OAuth/ADC credentials but never reuses the TEST spreadsheet ID.
Set the already-supported variables in the terminal that runs ResearchRadar:

```bash
export GOOGLE_LIVE_PILOT_SPREADSHEET_ID="<LIVE_PILOT_SPREADSHEET_ID>"
export RESEARCH_RADAR_SHEETS_ENV="live-pilot"
export RESEARCH_RADAR_DATA_MODE="live"
```

The workbook title must be exactly `ResearchRadar AI — LIVE PILOT`. These commands are read-only:

```bash
research-radar sheets-status --live
research-radar sheets-init --live --dry-run
research-radar sheets-sync --live --dry-run --reference-date 2026-10-12
```

After a separately recorded worksheet-initialization authorization, create only missing approved
worksheets with:

```bash
research-radar sheets-init --live --apply
```

The command requires the exact live mode, live-pilot environment, configured pilot ID, title, and
explicit flag. `sheets-sync --live --apply` remains disabled and requires a different future
authorization.
