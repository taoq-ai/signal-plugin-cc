# signal-plugin-cc

Answer Claude Code's permission prompts and questions from Signal when you're away from your Mac.
It works in any Claude Code session (desktop app, terminal, IDE) because it is a set of hooks, not a CLI mode.

- **Permission prompts:** the bot sends you the tool and its command or file. Reply `y` to allow, `n` to deny,
  or anything else to deny and tell Claude why ("use the test database").
- **Questions (AskUserQuestion):** the bot sends the questions with numbered options. Reply one line per
  question with an option number (`1,3` for multi-select) or your own answer.
- **Waiting for input:** when a session finishes and waits for you, the bot tells you.

It only relays while you're away: if your Mac has had keyboard or mouse input in the last 60 seconds, Claude Code
shows its normal prompt. If you come back while a prompt is waiting on Signal, it hands the prompt back to the Mac.
No reply within 5 minutes also hands it back. Without a config file the plugin does nothing.

## Setup

1. Install signal-cli (it brings Java) and qrencode:

   ```bash
   brew install signal-cli qrencode
   ```

2. Link signal-cli to Signal. Pick one:

   **Your own number (simplest).** signal-cli becomes a linked device on your account, and prompts arrive in
   Note to Self, sent so that your phone still notifies. Like any linked device, signal-cli then receives your
   messages and stores them in `~/.local/share/signal-cli`. This opens the QR code in Preview; scan it from
   Signal → Settings → Linked devices → Link new device:

   ```bash
   L="$TMPDIR/signal-link.txt"; signal-cli link -n "Claude relay" > "$L" 2>&1 & until grep -q sgnl:// "$L" 2>/dev/null; do sleep 1; done; qrencode -o "$TMPDIR/signal-link.png" "$(grep -o 'sgnl://[^ ]*' "$L")" && open "$TMPDIR/signal-link.png"; wait; cat "$L"
   ```

   **A separate bot number.** The bot messages you like any contact and never sees your own messages. You need
   a second number that can receive an SMS (a prepaid SIM) or a call (a landline); Signal blocks many VoIP
   numbers. Signal requires a captcha: open https://signalcaptchas.org/registration/generate.html, solve it,
   then right-click "Open Signal" and copy the link (clicking it hands the token to Signal Desktop instead).

   ```bash
   signal-cli -a +BOTNUMBER register --captcha 'signalcaptcha://...'
   signal-cli -a +BOTNUMBER verify CODE
   signal-cli -a +BOTNUMBER setPin YOUR-PIN
   signal-cli -a +BOTNUMBER updateProfile --given-name Claude
   ```

3. Write `~/.config/signal-plugin-cc/config.json`:

   ```json
   {"owner": "+YOURNUMBER"}
   ```

   With a bot number, add `"bot": "+BOTNUMBER"`. Optional keys: `wait` (seconds to wait for a reply, default
   300, at most 3500), `idle` (seconds without input before the Mac counts as unattended, default 60), `port`
   (signal-cli daemon port, default 8299), `signal_cli` (path to signal-cli). Only replies from `owner` are read.
   A misspelled or missing key is reported on stderr and turns the plugin off.

4. Install the plugin in Claude Code:

   ```
   /plugin marketplace add taoq-ai/signal-plugin-cc
   /plugin install signal@signal-plugin-cc
   ```

5. Start a new session. It starts the signal-cli daemon if it isn't running (log in
   `~/.config/signal-plugin-cc/daemon.log`). With a bot number, the first message may land in Signal's
   message requests; accept it.

## Several prompts at once

Each prompt starts with a tag like `[a3f1]`. If only one prompt is waiting, just reply. If several are waiting,
reply to the message in Signal (swipe to quote it) or start your reply with its tag.

## Security

Anyone who can send messages as `owner` can approve tool calls in your sessions. Keep registration lock on
for your number (and the bot's). Plan approval (ExitPlanMode) is never relayed; it stays on the Mac.

## Limits

- While a prompt waits on Signal, the Mac doesn't show it; touching the keyboard or mouse hands it back.
- Idle detection is macOS only. Elsewhere every prompt goes to Signal first, so lower `wait`.
- signal-cli is an unofficial client; a Signal protocol change can break it until signal-cli updates.
- Signal deregisters accounts that stay unused for a long time; keep at least one session running now and then.

## Development

```bash
python3 -m unittest discover -s tests
```
