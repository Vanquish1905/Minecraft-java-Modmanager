"""Reusable widgets and helpers for the Tk interface."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..platform_utils import IS_MAC


def bind_right_click(widget: tk.Misc, handler: Callable) -> None:
    if IS_MAC:
        widget.bind("<Button-2>", handler)
        widget.bind("<Control-Button-1>", handler)
    else:
        widget.bind("<Button-3>", handler)


def wheel_steps(event) -> int:
    """Scroll direction for <MouseWheel>/<Button-4/5> on Windows, macOS and X11."""
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1
    delta = getattr(event, "delta", 0)
    if not delta:
        return 0
    if IS_MAC:
        return -1 if delta > 0 else 1
    return -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120)


def bind_wheel(area: tk.Widget, target) -> None:
    """Scroll `target` (anything with yview_scroll) while the mouse is over `area`."""
    def on_wheel(e):
        steps = wheel_steps(e)
        if steps:
            target.yview_scroll(steps, "units")
        return "break"

    def enter(_):
        area.bind_all("<MouseWheel>", on_wheel)
        area.bind_all("<Button-4>", on_wheel)
        area.bind_all("<Button-5>", on_wheel)

    def leave(_):
        area.unbind_all("<MouseWheel>")
        area.unbind_all("<Button-4>")
        area.unbind_all("<Button-5>")

    area.bind("<Enter>", enter, add="+")
    area.bind("<Leave>", leave, add="+")


def make_tree(parent, columns: list[tuple[str, str, int]], show_tree: bool = False,
              selectmode: str = "extended") -> tuple[ttk.Frame, ttk.Treeview]:
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="tree headings" if show_tree else "headings",
                        selectmode=selectmode)
    for n, (cid, title, width) in enumerate(columns):
        tree.heading(cid, text=title, anchor="w")
        tree.column(cid, width=width, minwidth=40, stretch=width > 150 or n == len(columns) - 1, anchor="w")
    if show_tree:
        tree.column("#0", width=36, stretch=False)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    sb.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree


def center_on(win: tk.Toplevel, parent: Optional[tk.Misc]) -> None:
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    if parent is not None and parent.winfo_ismapped():
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
    else:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class Dialog(tk.Toplevel):
    """Base class for modal-ish themed dialogs."""

    def __init__(self, app, title: str, modal: bool = True, parent: tk.Misc | None = None):
        parent = parent or app.root
        super().__init__(parent)
        self.app = app
        self.title(title)
        app.theme.toplevel(self)
        self.transient(parent)
        # Buttons are packed first so they stay visible when the window is small.
        self.buttons = ttk.Frame(self, padding=(14, 0, 14, 14))
        self.buttons.pack(side="bottom", fill="x")
        self.body = ttk.Frame(self, padding=14)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._modal = modal
        self._parent = parent

    def show(self):
        center_on(self, self._parent)
        if self._modal:
            self.wait_visibility()
            try:
                self.grab_set()
            except tk.TclError:
                pass
        self.focus_set()
        return self

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class TaskRunner:
    """Runs work on background threads and delivers results on the Tk thread."""

    def __init__(self, root: tk.Tk, on_status: Callable[[str, Optional[float], bool], None]):
        self.root = root
        self.q: "queue.Queue[tuple[Callable, tuple]]" = queue.Queue()
        self.on_status = on_status
        self.active = 0
        self.cancel_event: Optional[threading.Event] = None
        self._poll()

    def post(self, fn: Callable, *args) -> None:
        self.q.put((fn, args))

    def _poll(self):
        try:
            for _ in range(200):
                fn, args = self.q.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def run(self, work: Callable, on_done: Callable | None = None, on_error: Callable | None = None,
            label: str = "Working...", parent: tk.Misc | None = None, quiet: bool = False) -> threading.Event:
        """work(progress, cancel_event) runs in a thread; on_done(result) on the UI thread."""
        cancel = threading.Event()
        self.cancel_event = cancel
        self.active += 1
        if not quiet:
            self.on_status(label, None, True)

        def progress(text: str, frac: Optional[float] = None):
            if not quiet:
                self.post(self.on_status, text, frac, True)

        def finish():
            self.active -= 1
            if self.active <= 0:
                self.active = 0
                self.on_status("Ready", None, False)

        def thread():
            try:
                result = work(progress, cancel)
            except BaseException as e:  # noqa: BLE001 - report everything to the user
                tb = traceback.format_exc()

                def fail(e=e, tb=tb):
                    finish()
                    if on_error:
                        on_error(e)
                    elif type(e).__name__ != "Cancelled":
                        print(tb)
                        messagebox.showerror("Error", str(e) or type(e).__name__, parent=parent or self.root)
                self.post(fail)
                return

            def ok(result=result):
                finish()
                if on_done:
                    on_done(result)
            self.post(ok)

        threading.Thread(target=thread, daemon=True).start()
        return cancel

    def cancel(self):
        if self.cancel_event:
            self.cancel_event.set()


class LabeledEntry(ttk.Frame):
    def __init__(self, parent, label: str, var: tk.Variable, width: int = 30, browse: Callable | None = None):
        super().__init__(parent)
        ttk.Label(self, text=label).pack(side="left")
        ttk.Entry(self, textvariable=var, width=width).pack(side="left", fill="x", expand=True, padx=6)
        if browse:
            ttk.Button(self, text="Browse...", command=browse).pack(side="left")
