# OpenClaw Streamlined Setup

This is a small local Windows desktop wrapper for running an OpenClaw install through PowerShell with a simpler GUI.

## What it does

- Runs the install in the background from a Windows app
- Locks provider selection to OpenAI during the guided flow
- Passes through to a PowerShell setup command you control
- Automatically continues into `openclaw config --section gateway` after install
- Embeds a real PowerShell-style terminal in the app for interactive config prompts
- Supports arrow keys and terminal-style interaction inside the window
- Saves your default model and commands into `config.json`

## Run it

```powershell
python .\app.py
```

The app now uses:

- `pywinpty` for a Windows PTY backend
- `pyte` for terminal screen rendering

## How to use it

1. Leave the provider locked to OpenAI.
2. Leave the recommended model on `openai/gpt-5.4`, or type another valid OpenAI model name.
3. Leave the default install command as `irm https://openclaw.ai/install.ps1 | iex`.
4. Leave the default config command as `openclaw config --section gateway`.
5. Click inside the embedded terminal before using arrows, Enter, or paste.
6. Click `Start Setup`.
7. Enter the API key and answer the rest of the OpenClaw questions directly in the embedded terminal.

The command fields support the `{model}` placeholder for the selected OpenAI model.

Example:

```powershell
irm https://openclaw.ai/install.ps1 | iex
```

If you keep the default hosted installer, the app will inject OpenAI-focused environment variables before running install and config:

- `OPENAI_MODEL`
- `OPENAI_PROVIDER`
- `OPENCLAW_OPENAI_MODEL`
- `OPENCLAW_PROVIDER`

The wrapper also tries to pre-write `agents.defaults.model.primary` to your selected OpenAI model before it launches the gateway-only config section.

If your setup is a script in another folder instead, you can point at it directly:

```powershell
& "C:\path\to\your\setup.ps1" -Provider openai -Model "{model}"
```

## Files

- `app.py`: Tkinter GUI plus embedded PTY-backed terminal
- `scripts/install_openclaw.ps1`: background PowerShell runner
- `config.json`: saved model and command defaults, created after the first run

## Packaging as an .exe

Right now this project is still a Python app. That is completely fine if you are running it locally with Python installed.

If you want to hand it to other people more easily, build the `.exe` version with:

```powershell
.\build_exe.bat
```

That creates a packaged folder here:

```text
dist\OpenClawSetup
```

If you prefer to build manually, you can still use:

```powershell
python -m pip install -r .\requirements.txt pyinstaller
pyinstaller --noconsole --onefile --name OpenClawSetup .\app.py
```

Then keep `scripts\install_openclaw.ps1` next to the built executable in a `scripts` folder, which `build_exe.bat` already handles for you.
