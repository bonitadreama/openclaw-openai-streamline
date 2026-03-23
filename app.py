import json
import os
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import pyte
from winpty import Backend, PtyProcess


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
SCRIPT_PATH = APP_DIR / "scripts" / "install_openclaw.ps1"
DEFAULT_SETUP_COMMAND = "irm https://openclaw.ai/install.ps1 | iex"
DEFAULT_CONFIG_COMMAND = "openclaw config --section gateway"
DEFAULT_MODEL = "openai/gpt-5.4"
MODEL_PRESETS = [
    "openai/codex-mini-latest",
    "openai/gpt-4",
    "openai/gpt-4-turbo",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "openai/gpt-4o",
    "openai/gpt-4o-2024-05-13",
    "openai/gpt-4o-2024-08-06",
    "openai/gpt-4o-2024-11-20",
    "openai/gpt-4o-mini",
    "openai/gpt-5",
    "openai/gpt-5-chat-latest",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "openai/gpt-5-pro",
    "openai/gpt-5-codex",
    "openai/gpt-5.1",
    "openai/gpt-5.1-chat-latest",
    "openai/gpt-5.1-codex",
    "openai/gpt-5.1-codex-max",
    "openai/gpt-5.1-codex-mini",
    "openai/gpt-5.2",
    "openai/gpt-5.2-chat-latest",
    "openai/gpt-5.2-codex",
    "openai/gpt-5.2-pro",
    "openai/gpt-5.3-codex",
    "openai/gpt-5.4",
    "openai/gpt-5.4-pro",
    "openai/o1",
    "openai/o1-pro",
    "openai/o3",
    "openai/o3-deep-research",
    "openai/o3-mini",
    "openai/o3-pro",
    "openai/o4-mini",
    "openai/o4-mini-deep-research",
    "openai-codex/gpt-5.1",
    "openai-codex/gpt-5.1-codex-max",
    "openai-codex/gpt-5.1-codex-mini",
    "openai-codex/gpt-5.2",
    "openai-codex/gpt-5.2-codex",
    "openai-codex/gpt-5.3-codex",
    "openai-codex/gpt-5.3-codex-spark",
    "openai-codex/gpt-5.4",
]

KEY_MAP = {
    "Return": "\r",
    "BackSpace": "\x7f",
    "Tab": "\t",
    "Escape": "\x1b",
    "Up": "\x1b[A",
    "Down": "\x1b[B",
    "Right": "\x1b[C",
    "Left": "\x1b[D",
    "Home": "\x1b[H",
    "End": "\x1b[F",
    "Delete": "\x1b[3~",
    "Prior": "\x1b[5~",
    "Next": "\x1b[6~",
}


class EmbeddedTerminal:
    def __init__(self, widget: tk.Text, status_var: tk.StringVar) -> None:
        self.widget = widget
        self.status_var = status_var
        self.font = tkfont.Font(font=self.widget["font"])
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.process: PtyProcess | None = None
        self.reader_thread: threading.Thread | None = None
        self.screen: pyte.HistoryScreen | None = None
        self.stream: pyte.ByteStream | None = None
        self.cols = 120
        self.rows = 32
        self._configure_screen(self.rows, self.cols)
        self.widget.bind("<KeyPress>", self._on_keypress)
        self.widget.bind("<Configure>", self._on_resize)
        self.widget.bind("<<Paste>>", self._on_paste)
        self.widget.bind("<Button-1>", self._focus_terminal)
        self.widget.after(33, self._drain_queue)

    def _configure_screen(self, rows: int, cols: int) -> None:
        self.rows = max(24, rows)
        self.cols = max(80, cols)
        history = 2000
        self.screen = pyte.HistoryScreen(self.cols, self.rows, history=history)
        self.stream = pyte.ByteStream()
        self.stream.attach(self.screen)

    def clear(self) -> None:
        self._configure_screen(self.rows, self.cols)
        self._render()

    def is_running(self) -> bool:
        return self.process is not None and self.process.isalive()

    def start(self, argv: list[str], env: dict[str, str], cwd: str) -> None:
        self.clear()
        self.process = PtyProcess.spawn(
            argv,
            cwd=cwd,
            env=env,
            dimensions=(self.rows, self.cols),
            backend=Backend.ConPTY,
        )
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self.status_var.set("Running setup...")
        self.widget.focus_set()

    def terminate(self) -> None:
        if self.process is None:
            return
        try:
            self.process.terminate()
        except OSError:
            pass

    def send_text(self, text: str) -> None:
        if not self.is_running():
            return
        try:
            assert self.process is not None
            self.process.write(text)
        except OSError:
            self.output_queue.put(("system", "\r\n[local] Could not write to terminal.\r\n"))

    def _reader_loop(self) -> None:
        assert self.process is not None
        try:
            while self.process.isalive():
                data = self.process.read(4096)
                if not data:
                    break
                self.output_queue.put(("data", data))
        except EOFError:
            pass
        except OSError as exc:
            self.output_queue.put(("system", f"\r\n[local] Terminal read error: {exc}\r\n"))
        finally:
            exit_code = 0
            try:
                exit_code = self.process.wait()
            except OSError:
                exit_code = 1
            self.output_queue.put(("exit", str(exit_code)))

    def _drain_queue(self) -> None:
        dirty = False
        try:
            while True:
                kind, payload = self.output_queue.get_nowait()
                if kind == "data":
                    assert self.stream is not None
                    self.stream.feed(payload.encode("utf-8", "replace"))
                    dirty = True
                elif kind == "system":
                    assert self.stream is not None
                    self.stream.feed(payload.encode("utf-8", "replace"))
                    dirty = True
                elif kind == "exit":
                    self.status_var.set("Completed" if payload == "0" else f"Failed ({payload})")
                    self.process = None
                    dirty = True
        except queue.Empty:
            pass

        if dirty:
            self._render()

        self.widget.after(33, self._drain_queue)

    def _render(self) -> None:
        assert self.screen is not None
        display = list(self.screen.display)
        lines = display[-self.rows :]

        self.widget.configure(state="normal")
        self.widget.delete("1.0", "end")
        text = "\n".join(line.rstrip() for line in lines)
        self.widget.insert("1.0", text)

        self.widget.yview_moveto(0.0)
        self.widget.configure(state="disabled")

    def _on_keypress(self, event: tk.Event) -> str:
        if not self.is_running():
            return "break"

        if event.state & 0x4 and event.keysym.lower() == "c":
            self.send_text("\x03")
            return "break"

        if event.state & 0x4 and event.keysym.lower() == "v":
            self._send_clipboard()
            return "break"

        mapped = KEY_MAP.get(event.keysym)
        if mapped is not None:
            self.send_text(mapped)
            return "break"

        if event.char and event.char >= " ":
            self.send_text(event.char)
            return "break"

        return "break"

    def _send_clipboard(self) -> None:
        try:
            clipboard = self.widget.clipboard_get()
        except tk.TclError:
            return
        self.send_text(clipboard)

    def _on_paste(self, event: tk.Event) -> str:
        self._send_clipboard()
        return "break"

    def _focus_terminal(self, event: tk.Event) -> str:
        self.widget.focus_set()
        return "break"

    def _on_resize(self, event: tk.Event) -> None:
        char_width = max(self.font.measure("M"), 1)
        line_height = max(self.font.metrics("linespace"), 1)
        cols = max(80, (event.width - 24) // char_width)
        rows = max(24, (event.height - 24) // line_height)

        if cols == self.cols and rows == self.rows:
            return

        self.cols = cols
        self.rows = rows
        if self.screen is not None:
            self.screen.resize(self.rows, self.cols)
        if self.process is not None and self.process.isalive():
            try:
                self.process.setwinsize(self.rows, self.cols)
            except OSError:
                pass
        self._render()


class OpenClawInstallerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("OpenClaw Streamlined Setup")
        self.root.geometry("980x760")
        self.root.minsize(860, 680)

        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.command_var = tk.StringVar(value=DEFAULT_SETUP_COMMAND)
        self.config_command_var = tk.StringVar(value=DEFAULT_CONFIG_COMMAND)
        self.status_var = tk.StringVar(value="Idle")
        self.persist_model_var = tk.BooleanVar(value=True)
        self.auto_config_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._load_config()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=18)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="OpenClaw Streamlined Setup", font=("Segoe UI Semibold", 18)).grid(row=0, column=0, sticky="w")

        body = ttk.Frame(self.root, padding=(18, 0, 18, 18))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        config_card = ttk.LabelFrame(body, text="Install Options", padding=16)
        config_card.grid(row=0, column=0, sticky="ew")
        config_card.columnconfigure(1, weight=1)

        ttk.Label(config_card, text="Provider").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Label(config_card, text="OpenAI only", foreground="#1d4ed8").grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(config_card, text="Preferred model").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Combobox(config_card, textvariable=self.model_var, values=MODEL_PRESETS, state="normal").grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(
            config_card,
            text="Recommended: openai/gpt-5.4. You can still type any valid OpenAI model name.",
            wraplength=520,
        ).grid(row=1, column=2, sticky="w", padx=(10, 0), pady=6)

        ttk.Label(config_card, text="Install command").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(config_card, textvariable=self.command_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(config_card, text="Config command").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(config_card, textvariable=self.config_command_var).grid(row=3, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(
            config_card,
            text="The app pre-seeds your selected OpenAI model, then runs the gateway section so the broader model wizard is skipped by default.",
            wraplength=760,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 6))

        ttk.Checkbutton(
            config_card,
            text="Persist selected model into child process environment",
            variable=self.persist_model_var,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 0))

        ttk.Checkbutton(
            config_card,
            text="Run OpenClaw config automatically after install",
            variable=self.auto_config_var,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 0))

        terminal_card = ttk.LabelFrame(body, text="Embedded PowerShell", padding=16)
        terminal_card.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        terminal_card.columnconfigure(0, weight=1)
        terminal_card.rowconfigure(0, weight=1)

        self.terminal_text = tk.Text(
            terminal_card,
            wrap="none",
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="#f8fafc",
            relief="flat",
            padx=12,
            pady=12,
            font=("Consolas", 11),
            state="disabled",
        )
        self.terminal_text.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(terminal_card, orient="vertical", command=self.terminal_text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(terminal_card, orient="horizontal", command=self.terminal_text.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.terminal_text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        footer = ttk.Frame(body, padding=(0, 14, 0, 0))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)

        ttk.Button(footer, text="Start Setup", command=self.start_install).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Stop", command=self.stop_install).grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(footer, text="Tip: click inside the terminal before using arrows, Enter, or paste.").grid(row=0, column=2, sticky="w", padx=(16, 0))
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=3, sticky="e", padx=(16, 0))

        self.terminal = EmbeddedTerminal(self.terminal_text, self.status_var)

    def _load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return

        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            messagebox.showerror("Config error", f"Could not load config.json:\n{exc}")
            return

        self.model_var.set(data.get("model", self.model_var.get()) or DEFAULT_MODEL)
        self.command_var.set(data.get("setup_command", self.command_var.get()))
        self.config_command_var.set(data.get("config_command", self.config_command_var.get()))
        self.persist_model_var.set(bool(data.get("persist_model", True)))
        self.auto_config_var.set(bool(data.get("auto_config", True)))

    def _save_config(self) -> None:
        payload = {
            "model": self.model_var.get().strip(),
            "setup_command": self.command_var.get().strip(),
            "config_command": self.config_command_var.get().strip(),
            "persist_model": self.persist_model_var.get(),
            "auto_config": self.auto_config_var.get(),
        }

        try:
            CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save config.json:\n{exc}")
            return

        self.status_var.set("Defaults saved")

    def start_install(self) -> None:
        if self.terminal.is_running():
            messagebox.showinfo("Already running", "The installer is already running.")
            return

        model = self.model_var.get().strip()
        setup_command = self.command_var.get().strip()
        config_command = self.config_command_var.get().strip()

        if not model:
            messagebox.showerror("Missing model", "Choose or type an OpenAI model first.")
            return
        if not setup_command:
            messagebox.showerror("Missing command", "Enter the PowerShell install command to run.")
            return
        if self.auto_config_var.get() and not config_command:
            messagebox.showerror("Missing config command", "Enter the OpenClaw config command to run after install.")
            return
        if not SCRIPT_PATH.exists():
            messagebox.showerror("Missing script", f"Could not find:\n{SCRIPT_PATH}")
            return

        self._save_config()

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["OPENAI_MODEL"] = model
        env["OPENAI_PROVIDER"] = "openai"
        env["OPENCLAW_PROVIDER"] = "openai"
        if self.persist_model_var.get():
            env["OPENCLAW_OPENAI_MODEL"] = model
        argv = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Model",
            model,
            "-SetupCommand",
            setup_command,
        ]
        if self.auto_config_var.get():
            argv.extend(["-ConfigCommand", config_command, "-AutoConfigure"])
        if self.persist_model_var.get():
            argv.append("-PersistModel")

        try:
            self.terminal.start(argv, env=env, cwd=str(APP_DIR))
        except Exception as exc:
            messagebox.showerror("Launch failed", f"Could not start the embedded terminal:\n{exc}")
            self.status_var.set("Failed to launch")

    def stop_install(self) -> None:
        if not self.terminal.is_running():
            self.status_var.set("No active process")
            return
        self.terminal.terminate()
        self.status_var.set("Stopping...")


def main() -> None:
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except tk.TclError:
        pass
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    OpenClawInstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
