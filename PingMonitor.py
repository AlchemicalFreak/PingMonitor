#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PingMonitor.py — фінальна версія
- PyQt6 GUI (українська)
- групи, примітки, пошук
- Telegram повідомлення (async)
- пінг (IPv4, fallback IPv6), без мерехтіння консолі на Windows
- автоматичне оновлення через GitHub Releases (version.json)
- збереження конфігу в %APPDATA%/PingMonitor
- готово для PyInstaller (--onefile --noconsole --icon=icon.ico)
"""

from __future__ import annotations
import sys
import os
import json
import subprocess
import time
import threading
import tempfile
import requests
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtGui import QIcon


# ---------------------------
# Конфіг та Telegram (вставлено)
# ---------------------------
TELEGRAM_TOKEN = "8446791342:AAFo1iHvk6dmquwtr3AJ2BcD-9mIxUzCC00"
CHAT_ID = "-1003368463307"

CURRENT_VERSION = "1.0.1"
UPDATE_JSON_URL = "https://raw.githubusercontent.com/AlchemicalFreak/PingMonitor/main/version.json"

# ---------------------------
# Шляхи
# ---------------------------
APPDATA_ENV = os.getenv("APPDATA")
if APPDATA_ENV:
    APP_DIR = Path(APPDATA_ENV) / "PingMonitor"
else:
    APP_DIR = Path.home() / ".pingmonitor"
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DIR / "config.json"
GROUP_COLORS_FILE = APP_DIR / "group_colors.json"
LOG_FILE = APP_DIR / "monitor.log"
ICON_FILE = Path(__file__).parent / "icon.ico"

# ---------------------------
# Дефолтні групи / кольори
# ---------------------------
DEFAULT_GROUPS = ["Сервер", "БУВ", "Камера", "ПК", "Принтер", "Табло", "Реєстратор"]
DEFAULT_GROUP_COLORS = {
    "Табло": "#FFEFD5",        # світлий
    "Реєстратор": "#FFFF00",
    "Принтер": "#FF4500",
    "Сервер": "#1E90FF",
    "БУВ": "#7CFC00",
    "Камера": "#20B2AA",
    "ПК": "#C080FF"
}

# ---------------------------
# Утиліти
# ---------------------------
def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def write_log(line: str):
    s = f"[{now_ts()}] {line}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass

# ---------------------------
# Конфіг load/save
# ---------------------------
def ensure_default_config():
    if not CONFIG_FILE.exists():
        cfg = {"entries": [], "ping_interval": 5, "ping_timeout": 1}
        save_config(cfg)
    if not GROUP_COLORS_FILE.exists():
        save_group_colors(DEFAULT_GROUP_COLORS)

def load_config() -> Dict:
    ensure_default_config()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if "entries" not in cfg:
            cfg["entries"] = []
        if "ping_interval" not in cfg:
            cfg["ping_interval"] = 5
        if "ping_timeout" not in cfg:
            cfg["ping_timeout"] = 1
        return cfg
    except Exception as e:
        write_log(f"Помилка load_config: {e}")
        return {"entries": [], "ping_interval": 5, "ping_timeout": 1}

def save_config(cfg: Dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        write_log(f"Помилка save_config: {e}")

def load_group_colors() -> Dict[str, str]:
    try:
        if GROUP_COLORS_FILE.exists():
            with open(GROUP_COLORS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            save_group_colors(DEFAULT_GROUP_COLORS)
            return DEFAULT_GROUP_COLORS.copy()
    except Exception as e:
        write_log(f"Помилка load_group_colors: {e}")
        return DEFAULT_GROUP_COLORS.copy()

def save_group_colors(data: Dict[str, str]):
    try:
        with open(GROUP_COLORS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        write_log(f"Помилка save_group_colors: {e}")

# ---------------------------
# Telegram: синхронний і async wrapper
# ---------------------------
def send_telegram(text: str) -> bool:
    """Відправка повідомлення синхронно. Повертає True якщо 200."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        write_log("Telegram: токен/чат не вказано")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=8)
        write_log(f"Telegram send status: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        write_log(f"Telegram send exception: {e}")
        return False

def send_telegram_async(text: str):
    def _t():
        try:
            send_telegram(text)
        except Exception as e:
            write_log(f"send_telegram_async exception: {e}")
    threading.Thread(target=_t, daemon=True).start()

# ---------------------------
# Ping: IPv4 then IPv6 fallback; no console on Windows
# returns (ok: bool, rtt_ms: Optional[int], used_addr: Optional[str])
# ---------------------------
def ping_host(addr: str, timeout_s: float = 1.0) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Спробуємо пінг по дефолту (система вибирає сімейство).
    Якщо не відповів — спробуємо примусово IPv6 (-6) на Windows / Linux.
    Повертаємо (ok, rtt_ms_if_ok, used_addr_string_or_None)
    """
    start = time.time()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # First try: system default
    if sys.platform.startswith("win"):
        cmd = ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), addr]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_s))), addr]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             timeout=timeout_s + 1, creationflags=creationflags)
        elapsed_ms = int((time.time() - start) * 1000)
        if res.returncode == 0:
            # try to parse IP from output
            used = parse_ip_from_ping_stdout(res.stdout)
            return True, elapsed_ms, used
    except Exception as e:
        write_log(f"ping_host exception (default) for {addr}: {e}")

    # Fallback: try IPv6 explicitly
    try:
        if sys.platform.startswith("win"):
            cmd6 = ["ping", "-6", "-n", "1", "-w", str(int(timeout_s * 1000)), addr]
        else:
            cmd6 = ["ping", "-6", "-c", "1", "-W", str(max(1, int(timeout_s))), addr]
        start2 = time.time()
        res6 = subprocess.run(cmd6, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              timeout=timeout_s + 1, creationflags=creationflags)
        elapsed6 = int((time.time() - start2) * 1000)
        if res6.returncode == 0:
            used6 = parse_ip_from_ping_stdout(res6.stdout)
            return True, elapsed6, used6
    except Exception as e:
        write_log(f"ping_host exception (ipv6) for {addr}: {e}")

    return False, None, None

def parse_ip_from_ping_stdout(text: str) -> Optional[str]:
    # Try to find '[' ... ']' e.g. "hostname [10.5.30.185]" or "PING host (10.5.30.185)"
    try:
        import re
        m = re.search(r"\[([0-9a-fA-F:\.]+)%?\d*\]", text)
        if m:
            return m.group(1)
        m2 = re.search(r"\(([0-9a-fA-F:\.]+)\)", text)
        if m2:
            return m2.group(1)
        # fallback: find first IPv4-like
        m3 = re.search(r"([0-9]{1,3}(?:\.[0-9]{1,3}){3})", text)
        if m3:
            return m3.group(1)
        # IPv6 fallback (simple)
        m4 = re.search(r"([0-9a-fA-F:]{2,})", text)
        if m4:
            return m4.group(1)
    except Exception:
        pass
    return None

# ---------------------------
# MonitorThread
# ---------------------------
class MonitorThread(QtCore.QThread):
    updated = QtCore.pyqtSignal(str, str, object)  # ip, state, rtt_ms
    log = QtCore.pyqtSignal(str)

    def __init__(self, get_entries_callable, interval_sec: float = 5.0, timeout_s: float = 1.0):
        super().__init__()
        self.get_entries = get_entries_callable
        self.interval = interval_sec
        self.timeout = timeout_s
        self._running = False
        self.last_state: Dict[str, Optional[bool]] = {}

    def run(self):
        self._running = True
        # initialize last_state snapshot
        try:
            entries = list(self.get_entries())
            for e in entries:
                ip = e.get("ip")
                if ip:
                    # start with None so initial ping when thread starts will set but not alert
                    self.last_state[ip] = None
        except Exception:
            pass

        while self._running:
            entries = list(self.get_entries())
            if not entries:
                # sleep in small steps
                for _ in range(int(self.interval * 10)):
                    if not self._running:
                        break
                    time.sleep(0.1)
                continue

            for e in entries:
                if not self._running:
                    break
                ip = e.get("ip")
                if not ip:
                    continue
                try:
                    ok, rtt, used = ping_host(ip, timeout_s=self.timeout)
                except Exception as ex:
                    ok, rtt, used = False, None, None
                    write_log(f"ping error for {ip}: {ex}")

                prev = self.last_state.get(ip)
                # if first time, set it without notification
                if prev is None:
                    self.last_state[ip] = ok
                    # emit update so GUI shows current status
                    state = "ONLINE" if ok else "OFFLINE"
                    self.updated.emit(ip, state, rtt)
                elif prev != ok:
                    # status changed -> notify
                    self.last_state[ip] = ok
                    state = "ONLINE" if ok else "OFFLINE"
                    msg = (
                        f"{'🟢' if ok else '🔴'} {ip} змінив статус:\n"
                        f"Статус: {'ONLINE' if ok else 'OFFLINE'}\n"
                        f"Час: {now_ts()}"
                    )
                    # send async, log, emit
                    try:
                        write_log(msg)
                        self.log.emit(msg)
                        send_telegram_async(msg)
                    except Exception as ex:
                        write_log(f"Error sending telegram on change: {ex}")
                    self.updated.emit(ip, state, rtt)
                else:
                    # no change - still emit update occasionally to refresh ping ms
                    state = "ONLINE" if ok else "OFFLINE"
                    self.updated.emit(ip, state, rtt)

                # small pause between pings to avoid burst
                for _ in range(3):
                    if not self._running:
                        break
                    time.sleep(0.02)

            # wait for interval but remain responsive
            for _ in range(int(self.interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.wait(2000)

# ---------------------------
# UI: MainWindow
# ---------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Панель моніторингу — PingMonitor v{CURRENT_VERSION}")
        try:
            if ICON_FILE.exists():
                self.setWindowTitle(f"Панель моніторингу — PingMonitor v{CURRENT_VERSION}")
        except Exception:
            pass
        self.resize(1024, 680)

        # state
        self.cfg = load_config()
        self.group_colors = load_group_colors()
        # ensure defaults present
        for g in DEFAULT_GROUPS:
            if g not in self.group_colors:
                self.group_colors[g] = DEFAULT_GROUP_COLORS.get(g, "#DDDDDD")
        save_group_colors(self.group_colors)

        self.monitor_thread: Optional[MonitorThread] = None
        self.status_map: Dict[str, bool] = {}

        # build UI
        self._build_ui()
        # fill table
        self._load_entries_into_table()

        # prepare thread object (not started)
        interval = self.cfg.get("ping_interval", 5)
        timeout = self.cfg.get("ping_timeout", 1)
        self.monitor_thread = MonitorThread(self._get_entries, interval_sec=interval, timeout_s=timeout)
        self.monitor_thread.updated.connect(self._on_update_from_thread)
        self.monitor_thread.log.connect(self._append_log)

        # theme
        self.current_theme = "dark"
        self.apply_dark_theme()

        # run auto-update check shortly after start
        QtCore.QTimer.singleShot(1500, self.auto_update_check)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(10,10,10,10)
        v.setSpacing(8)

        # top row: group combo, ip, note, add/delete
        top = QtWidgets.QHBoxLayout()
        self.combo_group = QtWidgets.QComboBox()
        for g in sorted(DEFAULT_GROUPS):
            self.combo_group.addItem(g)
        # add any extra groups from config
        extra = sorted(set([e.get("group","") for e in self.cfg.get("entries", [])]) - set(DEFAULT_GROUPS))
        for g in extra:
            if g:
                self.combo_group.addItem(g)

        self.input_ip = QtWidgets.QLineEdit(); self.input_ip.setPlaceholderText("IP або hostname")
        self.input_ip.setFixedWidth(300)
        self.input_note = QtWidgets.QLineEdit(); self.input_note.setPlaceholderText("Примітка")
        self.input_note.setFixedWidth(300)

        self.btn_add = QtWidgets.QPushButton("Додати")
        self.btn_delete = QtWidgets.QPushButton("Видалити")
        self.btn_add.clicked.connect(self.on_add)
        self.btn_delete.clicked.connect(self.on_delete_selected)

        top.addWidget(self.combo_group)
        top.addWidget(self.input_ip)
        top.addWidget(self.input_note)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_delete)
        top.addStretch()
        v.addLayout(top)

        # search
        search_row = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit(); self.search_input.setPlaceholderText("Пошук... (IP, примітка, група)")
        self.search_input.textChanged.connect(self.on_search_changed)
        search_row.addWidget(self.search_input)
        v.addLayout(search_row)

        # table
        self.table = QtWidgets.QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(["Група","IP-адреса","Примітка","Статус","Пінг (ms)"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setColumnWidth(0,140)
        self.table.setColumnWidth(1,180)
        self.table.setColumnWidth(2,300)
        self.table.setColumnWidth(3,120)
        self.table.setColumnWidth(4,100)
        v.addWidget(self.table)

        # buttons
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Запустити моніторинг")
        self.btn_stop = QtWidgets.QPushButton("Зупинити")
        self.btn_theme = QtWidgets.QPushButton("Світла тема")
        self.btn_clear_log = QtWidgets.QPushButton("Очистити лог")
        self.btn_test_telegram = QtWidgets.QPushButton("Тест Telegram")

        # style for button colors (fill background + border)
        # We'll tune these in apply_*_theme functions; set classes via objectName
        self.btn_stop.setObjectName("danger")
        self.btn_clear_log.setObjectName("danger")
        self.btn_delete.setObjectName("danger")
        self.btn_test_telegram.setObjectName("info")
        self.btn_theme.setObjectName("accent")

        self.btn_start.clicked.connect(self.start_monitoring)
        self.btn_stop.clicked.connect(self.stop_monitoring)
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_clear_log.clicked.connect(self.clear_log)
        self.btn_test_telegram.clicked.connect(self.test_telegram)

        self.btn_stop.setEnabled(False)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_theme)
        btn_row.addWidget(self.btn_clear_log)
        btn_row.addWidget(self.btn_test_telegram)
        btn_row.addStretch()

        self.label_status = QtWidgets.QLabel("Статус: зупинено")
        btn_row.addWidget(self.label_status)
        v.addLayout(btn_row)

        # log
        v.addWidget(QtWidgets.QLabel("Журнал подій:"))
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(10000)
        # load existing log
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    self.log_edit.setPlainText(f.read())
        except Exception:
            pass
        v.addWidget(self.log_edit, 1)

    # ---------------------------
    # table helpers
    # ---------------------------
    def _add_table_row(self, group: str, ip: str, note: str, status: str = "UNKNOWN", ping_ms: Optional[int]=None):
        r = self.table.rowCount()
        self.table.insertRow(r)

        item_group = QtWidgets.QTableWidgetItem(group)
        item_ip = QtWidgets.QTableWidgetItem(ip)
        item_note = QtWidgets.QTableWidgetItem(note)
        item_status = QtWidgets.QTableWidgetItem(status)
        item_ping = QtWidgets.QTableWidgetItem(str(ping_ms) if ping_ms is not None else "-")

        item_status.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        item_ping.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # group cell background only + choose readable foreground
        color_hex = self.group_colors.get(group, "#dddddd")
        try:
            bg = QtGui.QColor(color_hex)
            item_group.setBackground(QtGui.QBrush(bg))
            brightness = bg.red()*0.299 + bg.green()*0.587 + bg.blue()*0.114
            fg = QtGui.QColor("#000000") if brightness > 160 else QtGui.QColor("#ffffff")
            item_group.setForeground(QtGui.QBrush(fg))
        except Exception:
            pass

        self.table.setItem(r,0,item_group)
        self.table.setItem(r,1,item_ip)
        self.table.setItem(r,2,item_note)
        self.table.setItem(r,3,item_status)
        self.table.setItem(r,4,item_ping)

    def _find_row_by_ip(self, ip: str) -> Optional[int]:
        for r in range(self.table.rowCount()):
            it = self.table.item(r,1)
            if it and it.text() == ip:
                return r
        return None

    def _load_entries_into_table(self):
        self.table.setRowCount(0)
        for e in self.cfg.get("entries", []):
            group = e.get("group","")
            ip = e.get("ip","")
            note = e.get("note","")
            self._add_table_row(group, ip, note, status="UNKNOWN", ping_ms=None)

    def _get_entries(self):
        return list(self.cfg.get("entries", []))

    # ---------------------------
    # Actions: add / delete
    # ---------------------------
    def on_add(self):
        group = self.combo_group.currentText().strip()
        ip = self.input_ip.text().strip()
        note = self.input_note.text().strip()
        if not ip:
            return
        # avoid duplicates: same ip+group
        existing = [x for x in self.cfg.setdefault("entries", []) if x.get("ip")==ip and x.get("group")==group]
        if existing:
            QtWidgets.QMessageBox.information(self, "Інформація", "Такий IP уже існує в цій групі")
            self.input_ip.clear()
            self.input_note.clear()
            return

        entry = {"group": group, "ip": ip, "note": note}
        self.cfg["entries"].append(entry)
        save_config(self.cfg)
        self._add_table_row(group, ip, note, status="UNKNOWN", ping_ms=None)
        # ensure color exists
        if group not in self.group_colors:
            self.group_colors[group] = DEFAULT_GROUP_COLORS.get(group, "#DDDDDD")
            save_group_colors(self.group_colors)
        # log
        write_log(f"Додано {ip} ({note}) в групу {group}")
        self._append_log(f"Додано {ip} ({note}) в групу {group}")
        # Telegram: only addition message (variant B format)
        msg = (
            f"▶️ До моніторингу додано:\n"
            f"Група: {group}\n"
            f"IP: {ip}\n"
            f"Примітка: {note if note else '-'}"
        )
        send_telegram_async(msg)
        # clear inputs
        self.input_ip.clear()
        self.input_note.clear()

    def on_delete_selected(self):
        rows = sorted([idx.row() for idx in self.table.selectionModel().selectedRows()], reverse=True)
        if not rows:
            return
        for r in rows:
            ip_item = self.table.item(r,1)
            note_item = self.table.item(r,2)
            group_item = self.table.item(r,0)
            ip = ip_item.text() if ip_item else ""
            note = note_item.text() if note_item else ""
            group = group_item.text() if group_item else ""
            self.cfg["entries"] = [x for x in self.cfg.get("entries", []) if not (x.get("ip")==ip and x.get("group")==group)]
            self.table.removeRow(r)
            write_log(f"Видалено {ip} ({note}) з групи {group}")
            self._append_log(f"Видалено {ip} ({note}) з групи {group}")
            self.status_map.pop(ip, None)
            if self.monitor_thread and ip in self.monitor_thread.last_state:
                self.monitor_thread.last_state.pop(ip, None)
        save_config(self.cfg)

    # ---------------------------
    # Search/filter
    # ---------------------------
    def on_search_changed(self, text: str):
        t = text.lower().strip()
        for r in range(self.table.rowCount()):
            visible = False
            for c in range(self.table.columnCount()):
                it = self.table.item(r,c)
                if it and t in it.text().lower():
                    visible = True
                    break
            self.table.setRowHidden(r, not visible)

    # ---------------------------
    # Monitoring control
    # ---------------------------
    def start_monitoring(self):
        if not self.cfg.get("entries"):
            QtWidgets.QMessageBox.warning(self, "Увага", "Додайте хоча б один IP для моніторингу")
            return

        # recreate thread
        interval = self.cfg.get("ping_interval", 5)
        timeout = self.cfg.get("ping_timeout", 1)
        self.monitor_thread = MonitorThread(self._get_entries, interval_sec=interval, timeout_s=timeout)
        self.monitor_thread.updated.connect(self._on_update_from_thread)
        self.monitor_thread.log.connect(self._append_log)

        # send "Моніторинг запущено"
        send_telegram_async("📡 Моніторинг запущено")
        self._append_log("Моніторинг запущено")

        # initial ping for every entry and send status message
        for e in self.cfg.get("entries", []):
            ip = e.get("ip")
            group = e.get("group","")
            note = e.get("note","")
            try:
                ok, rtt, used = ping_host(ip, timeout_s=timeout)
            except Exception:
                ok, rtt, used = False, None, None
            # seed last_state so thread won't notify initial state again
            self.monitor_thread.last_state[ip] = ok
            # format Telegram message with emoji
            status_emoji = "🟢" if ok else "🔴"
            msg = (
                f"{status_emoji} Почато моніторинг:\n"
                f"Група: {group}\n"
                f"IP: {ip}\n"
                f"Примітка: {note if note else '-'}\n"
                f"Статус: {'ONLINE' if ok else 'OFFLINE'}"
            )
            if ok and rtt is not None:
                msg += f" ({rtt} ms)"
            send_telegram_async(msg)
            # update table immediately
            self._on_update_table_row(ip, "ONLINE" if ok else "OFFLINE", rtt)

        # start thread
        self.monitor_thread.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.label_status.setText("Статус: моніторинг запущено")
        write_log("Моніторинг запущено")

    def stop_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.label_status.setText("Статус: зупинено")
        self._append_log("Моніторинг зупинено")
        write_log("Моніторинг зупинено")

    # ---------------------------
    # Update from thread
    # ---------------------------
    def _on_update_from_thread(self, ip: str, state: str, rtt):
        # update GUI row
        self._on_update_table_row(ip, state, rtt)

    def _on_update_table_row(self, ip: str, state: str, rtt):
        r = self._find_row_by_ip(ip)
        if r is None:
            # add row if not present
            group = self.combo_group.currentText() if self.combo_group.currentText() else "Без групи"
            note = ""
            self.cfg.setdefault("entries", []).append({"group": group, "ip": ip, "note": note})
            save_config(self.cfg)
            self._add_table_row(group, ip, note, status=state, ping_ms=rtt)
            return
        # set status text with emoji
        status_text = "🟢 ONLINE" if state == "ONLINE" else "🔴 OFFLINE"
        self.table.item(r,3).setText(status_text)
        self.table.item(r,4).setText(str(rtt) if rtt is not None else "-")
        # ensure status text color visible
        if state == "ONLINE":
            self.table.item(r,3).setForeground(QtGui.QBrush(QtGui.QColor("#00c853")))
        else:
            self.table.item(r,3).setForeground(QtGui.QBrush(QtGui.QColor("#f39c12")))
        # update internal map
        self.status_map[ip] = (state == "ONLINE")

    # ---------------------------
    # Log UI
    # ---------------------------
    def _append_log(self, text: str):
        write_log(text)
        self.log_edit.appendPlainText(f"[{now_ts()}] {text}")

    def clear_log(self):
        try:
            open(LOG_FILE, "w", encoding="utf-8").close()
        except Exception:
            pass
        self.log_edit.setPlainText("")
        self._append_log("Лог очищено")

    # ---------------------------
    # Theme support (dark/light) + button colors
    # ---------------------------
    def toggle_theme(self):
        if self.current_theme == "dark":
            self.apply_light_theme()
            self.current_theme = "light"
            self.btn_theme.setText("Темна тема")
        else:
            self.apply_dark_theme()
            self.current_theme = "dark"
            self.btn_theme.setText("Світла тема")

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget { background-color: #0f1417; color: #d7e6dd; font-family: 'Segoe UI'; }
            QTableWidget { background-color: #0b0d0e; color: #d7e6dd; gridline-color: #121212; }
            QHeaderView::section { background-color: #0b0d0e; color: #a9cbb7; }
            QPushButton { background-color: #111314; color: #d7e6dd; border: 1px solid #1f7a1f; padding:6px; border-radius:6px; }
            QPushButton:hover { background-color: #17201a; }
            QPushButton#danger { background-color: #4a1f1f; border:1px solid #800; color:#fff; }
            QPushButton#info { background-color: #e6f5ff; border:1px solid #60a5fa; color:#003366; }
            QPushButton#accent { background-color: #ffb366; border:1px solid #ff8c1a; color:#222; }
            QLineEdit { background-color: #0b0d0e; color: #d7e6dd; border: 1px solid #111; padding:6px; border-radius:6px; }
            QPlainTextEdit { background-color: #060708; color: #cfead6; border: 1px solid #111; border-radius:8px; padding:8px; }
            QComboBox { background-color: #0b0d0e; color: #d7e6dd; border:1px solid #111; padding:6px; border-radius:6px;}
        """)
        # apply objectName styles
        self._apply_button_object_styles()

    def apply_light_theme(self):
        self.setStyleSheet("""
            QWidget { background-color: #f6f8f7; color: #071312; font-family: 'Segoe UI'; }
            QTableWidget { background-color: #ffffff; color: #071312; gridline-color: #ddd; border:1px solid #d0d0d0; }
            QHeaderView::section { background-color: #eef6ee; color: #1f6a1f; }
            QPushButton { background-color: #e9f5ef; color: #0b1a15; border: 1px solid #9ad19f; padding:6px; border-radius:6px; }
            QPushButton:hover { background-color: #dff0e6; }
            QPushButton#danger { background-color: #ffdddd; border:1px solid #ff4d4d; color:#660000; }
            QPushButton#info { background-color: #e6f5ff; border:1px solid #60a5fa; color:#003366; }
            QPushButton#accent { background-color: #ffefdb; border:1px solid #ff8c1a; color:#222; }
            QLineEdit { background-color: #ffffff; color: #071312; border: 1px solid #ddd; padding:6px; border-radius:6px; }
            QPlainTextEdit { background-color: #ffffff; color: #071312; border: 1px solid #ddd; border-radius:8px; padding:8px; }
            QComboBox { background-color: #ffffff; color: #071312; border:1px solid #ddd; padding:6px; border-radius:6px;}
        """)
        self._apply_button_object_styles()

    def _apply_button_object_styles(self):
        # apply styles for buttons based on objectName
        for btn in [self.btn_stop, self.btn_clear_log, self.btn_delete]:
            btn.setProperty("class", "danger")
        self.btn_test_telegram.setProperty("class", "info")
        self.btn_theme.setProperty("class", "accent")
        # refresh style
        for w in [self.btn_stop, self.btn_clear_log, self.btn_delete, self.btn_test_telegram, self.btn_theme]:
            w.style().unpolish(w)
            w.style().polish(w)

    # ---------------------------
    # Test Telegram
    # ---------------------------
    def test_telegram(self):
        msg = f"🔔 Тест від PingMonitor: {now_ts()}"
        dispatched = send_telegram(msg)
        if dispatched:
            self._append_log("Тестове повідомлення відправлено в Telegram")
        else:
            self._append_log("Не вдалось надіслати тестове повідомлення в Telegram (перевір токен/чат)")

    # ---------------------------
    # Auto-update (GitHub Releases)
    # ---------------------------
    def auto_update_check(self):
        try:
            upd = check_for_updates()
            if not upd:
                return
            latest_ver, url, changelog = upd
            dlg = QtWidgets.QMessageBox(self)
            dlg.setWindowTitle("Доступне оновлення")
            dlg.setText(f"Доступна нова версія {latest_ver}.\n\nЗміни:\n{changelog}\n\nЗавантажити та встановити?")
            dlg.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
            res = dlg.exec()
            if res == QtWidgets.QMessageBox.StandardButton.Yes:
                path = download_update(url)
                if path:
                    QtWidgets.QMessageBox.information(self, "Оновлення", "Файл завантажено. Інсталятор буде запущено.")
                    try:
                        os.startfile(path)
                    except Exception:
                        subprocess.Popen([path], shell=True)
                    QtCore.QCoreApplication.quit()
        except Exception as e:
            write_log(f"auto_update_check error: {e}")

# ---------------------------
# Auto-update helpers
# ---------------------------
def is_newer_version(v1: str, v2: str) -> bool:
    try:
        a = [int(x) for x in v1.split(".")]
        b = [int(x) for x in v2.split(".")]
        return a > b
    except Exception:
        return v1 != v2 and v1 > v2

def check_for_updates() -> Optional[Tuple[str,str,str]]:
    """
    Returns (latest_version, download_url, changelog) if newer found, else None
    """
    try:
        r = requests.get(UPDATE_JSON_URL, timeout=6)
        if r.status_code != 200:
            return None
        data = r.json()
        remote = data.get("version","")
        url = data.get("download_url","")
        changelog = data.get("changelog","")
        if remote and url and is_newer_version(remote, CURRENT_VERSION):
            return remote, url, changelog
        return None
    except Exception as e:
        write_log(f"check_for_updates error: {e}")
        return None

def download_update(url: str) -> Optional[str]:
    try:
        tmp = Path(tempfile.gettempdir()) / "PingMonitorUpdate.exe"
        write_log(f"Downloading update from {url} to {tmp}")
        r = requests.get(url, stream=True, timeout=20)
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1024*1024):
                if chunk:
                    f.write(chunk)
        return str(tmp)
    except Exception as e:
        write_log(f"download_update error: {e}")
        return None

# ---------------------------
# Entry point
# ---------------------------
def main():
    ensure_default_config()
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QIcon("icon.ico"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()