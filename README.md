# freeagent-ai

Generic mechanics and concepts for AI agents working with a FreeAgent account through the API.
Nothing here is specific to one business: no contact, project or bank-account IDs, no rates, no client rules.
Consuming repos keep those (see "Using this from a business repo").

## Contents

| Path | What |
|------|------|
| `freeagent_ai/` | Python client: credentials file, 401 auto-refresh, `login`, `status` |
| `docs/auth.md` | OAuth setup, credentials file, refresh, re-login |
| `docs/api-notes.md` | API behaviours and gotchas learned the hard way |
| `docs/timesheets.md` | Generic workflow for logging time |
| `docs/invoicing.md` | Generic workflow for draft invoices from timeslips |
| `docs/agent-rules.md` | Safety rules every agent should follow |

## Install

```bash
pip install -e ~/projects/freeagent-ai    # provides the `freeagent-ai` command and `import freeagent_ai`
```

## Use

```bash
freeagent-ai login     # opens the approve page; the user logs in and clicks Approve
freeagent-ai status    # confirms stored credentials work
```

```python
from freeagent_ai import call
call("GET", "users/me")
call("POST", "timeslips", {"timeslip": {...}})
```

## Using this from a business repo

The consuming repo owns the specifics and points agents here for the mechanics:

- Fixed IDs (user, contacts, projects, tasks, bank account, categories) and your OAuth app's client ID.
- Defaults (hours per day, billing rate, VAT, payment terms, invoice reference format).
- Client-specific delivery rules (e.g. a portal instead of email).
- Any tightening of `docs/agent-rules.md`.

Tests: `python3 -m unittest discover tests`.
