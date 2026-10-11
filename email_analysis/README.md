# Email Analysis

Local Windows desktop app. Offline `.eml`/`.mbox` imports use only the Python standard library. Optional Gmail import uses Google's supported OAuth desktop sign-in and Gmail API with the `gmail.readonly` scope. No cloud AI or mailbox writes. Outlook live access, `.msg` and `.pst` are not supported.

## Windows setup

Install Python 3.11 or newer from python.org with Tcl/Tk and the Windows Python launcher enabled. Double-click `START.cmd`, or run in PowerShell:

```powershell
cd .\emailAnalysis\email_analysis
.\run_python.cmd app.py
.\run_python.cmd -m unittest -v
```

Copy `config.example.json` to `config.json` to customize rules. Sender, subject, and body rules are case-insensitive substring matches. Each hit adds 0.15 to a base score of 0.55, capped at 0.95. Scores are rule-strength heuristics, not calibrated probabilities. Default: multiple categories, October 11, 2025 through October 11, 2026 inclusive, no email cap, attachments excluded, zero AI cost. Set inclusive `start_date`/`end_date` to `YYYY-MM-DD`, or null. `max_emails` is null for no limit or an integer cap on examined messages per import; a capped run may cover only part of the selected year. With one category enabled, the strongest match wins, with alphabetical tie breaking. Unmatched mail is Uncategorized. Scores below `review_threshold` need review.

## Connect Gmail locally

`run_python.cmd` uses this app's virtual environment first, then an installed Python launcher or Python, then the bundled Codex Python runtime when available. `SETUP_GMAIL.cmd` creates an ignored `.venv` and installs Gmail dependencies there. No system Python installation is modified.

Your connected Codex Gmail account does not grant this independent desktop application a token. Follow [Google's Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python) to create a Google Cloud project, enable Gmail API, configure OAuth consent, and create an OAuth client of type **Desktop app**. For testing, add your Gmail address as a test user. Save the downloaded client JSON as `email_analysis/private/gmail-client.json` (create `private` if needed). Never commit this file.

```powershell
.\SETUP_GMAIL.cmd
.\START.cmd
```

Click **Import Gmail (read-only)**, sign in in your browser, and grant read-only Gmail access. Tokens are stored in ignored `private/gmail-token.json`. The app lists and reads messages currently labeled INBOX in the configured period, using Europe/Berlin boundaries and Gmail's received timestamp. Archived/sent/spam/trash mail is excluded. The first import can take several minutes; the window shows progress. Repeating the same range avoids duplicates; already imported mail stays in the app even if subsequently archived. Completed imports survive a interrupted connection and can be retried. Delete `private/gmail-token.json` to disconnect locally and revoke the grant from your Google Account to revoke provider access. Google's testing-mode tokens may require repeat sign-in. OAuth and live mailbox access require your credentials and have not been tested against your real account.

Import one or more files. Reimports deduplicate by Message-ID or a hash of sender, subject, date, and decoded body. Corrections persist independently of predictions and survive reimport. Select an email and enter configured category names separated by commas to correct it. Search covers subject/body; sender and category/date filters narrow results. Analysis uses the filtered set and reports separate email and estimated thread counts, common senders, monthly counts, supporting excerpts, and clickable links opening imported emails. Category counts overlap in multi-category mode.

Gmail imports use provider thread IDs. Exported-file grouping uses the earliest References/In-Reply-To identifier, falling back to Message-ID or content identity. Incomplete exports can split conversations; the UI calls thread counts estimates because files may be mixed with Gmail data. Summaries are extractive previews of up to five recent emails per category. Action detection is English keyword based. Explicit deadlines recognize ISO dates only; today/tomorrow are inferred relative to the email timestamp. Other date forms remain undated. Verify every possible action and deadline against its supporting email.

## Evaluate your labeled sample

Import your sample, then choose **Export label template** and save it in `private`. Fill each ID's array with your independently assigned categories, for example `{"email-id": ["Finance"]}`. Choose **Evaluate labels** to report sample size, exact set-match accuracy, and micro precision/recall. Evaluation uses original automatic predictions even after corrections. Unknown IDs are reported and excluded. No personal labeled sample was provided, so personal-sample accuracy remains unverified. Synthetic tests cover import, duplicate handling, persistent correction, analysis, HTML/attachment handling, date limits, and evaluation separation.

## Privacy and limitations

All app storage is in `private/emails.db`, ignored by Git. Local config, email export extensions, label files and evaluation outputs are also ignored within this folder. Keep exports and generated files in `private`; files elsewhere in the repository may not be ignored. Email text is displayed as plain text; links, scripts and instructions in emails are never executed. Attachments are not stored or analyzed, and the Gmail importer never calls the attachment download API. SQLite and token files are not encrypted: protect your Windows account/disk and backups. **Delete imported data** removes stored emails and corrections and vacuums the database; original exports, label files, OAuth credentials, and external backups must be deleted separately. Classification rules are read at startup and affect new imports; existing predictions retain their original explanations. Changing rules for an existing sample requires deleting and reimporting it, which also clears corrections.

The application lives in `email_analysis` in [NELSOND19-DONT/emailAnalysis](https://github.com/NELSOND19-DONT/emailAnalysis). The Windows setup command above assumes you are in the parent of your downloaded or cloned `emailAnalysis` folder. `equipment_lab` belongs to the original TESTREPO and is not part of this repository.
