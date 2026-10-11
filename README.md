# Email Analysis

Local Windows app for understanding your Gmail inbox, correcting categories, and reviewing possible action items. Gmail access is read-only. No cloud AI, mailbox mutations, or attachment processing.

The app and [Windows setup instructions](email_analysis/README.md) are in `email_analysis`.

```powershell
cd .\email_analysis
.\SETUP_GMAIL.cmd
.\START.cmd
```

Gmail requires a Google OAuth Desktop client stored in `email_analysis/private/gmail-client.json`. Sign in with the app's Import Gmail button. Exported EML/MBOX files work without Gmail setup or third-party dependencies. The starter date range is October 11, 2025–October 11, 2026.

Keep credentials, exports, imported data, and human labels in `email_analysis/private`; never add them to Git. The repository contains source code and synthetic tests only. The original TESTREPO and its equipment lab remain separate.

Run tests from `email_analysis` with `.\run_python.cmd -m unittest -v`.
