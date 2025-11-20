#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PingMonitor.py — відновлена стабільна версія (варіант A)
- PyQt6 GUI (українська)
- групи, примітки, пошук
- Telegram повідомлення (async)
- пінг (IPv4, fallback IPv6)
- автоматичне оновлення через version.json
- збереження конфігу в %APPDATA%/PingMonitor
- QSplitter для регульованої висоти журналу подій
- кнопки з контурними кольорами та hover-ефектами (текст білий при hover)
- іконки для теми / telegram у верхньому правому кутку
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
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import requests

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QMessageBox

# ---------------------------
# Конфіг та Telegram
# ---------------------------
# !!! ЗАБЕРИ/СХОВАЙ свої токени перед пушем на GitHub
TELEGRAM_TOKEN = "PUT_YOUR_TOKEN_HERE"
CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"

CURRENT_VERSION = "1.0.3"
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
TELEGRAM_ICON = Path(__file__).parent / "telegram.ico"
LIGHT_THEME_ICON = Path(__file__).parent / "lighttheme.ico"
DARK_THEME_ICON = Path(__file__).parent / "darktheme.ico"

# ---------------------------
# Дефолтні групи / кольори
# ---------------------------
DEFAULT_GROUPS = ["Сервер", "БУВ", "Камера", "ПК", "Принтер", "Табло", "Реєстратор"]
DEFAULT_GROUP_COLORS = {
    "Табло": "#FFEFD5",
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
# Telegram
# ---------------------------
def send_telegram(text: str) -> bool:
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
# Ping helpers
# ---------------------------
def parse_ip_from_ping_stdout(text: str) -> Optional[str]:
    try:
        import re
        m = re.search(r"\[([0-9a-fA-F:\.]+)%?\d*\]", text)
        if m:
            return m.group(1)
        m2 = re.search(r"\(([0-9a-fA-F:\.]+)\)", text)
        if m2:
            return m2.group(1)
        m3 = re.search(r"([0-9]{1,3}(?:\.[0-9]{1,3}){3})", text)
        if m3:
            return m3.group(1)
        m4 = re.search(r"([0-9a-fA-F:]{2,})", text)
        if m4:
            return m4.group(1)
    except Exception:
        pass
    return None

def ping_host(addr: str, timeout_s: float = 1.0) -> Tuple[bool, Optional[int], Optional[str]]:
    start = time.time()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if sys.platform.startswith("win"):
        cmd = ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), addr]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_s))), addr]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             timeout=timeout_s + 1, creationflags=creationflags)
        elapsed_ms = int((time.time() - start) * 1000)
        if res.returncode == 0:
            used = parse_ip_from_ping_stdout(res.stdout)
            return True, elapsed_ms, used
    except Exception as e:
        write_log(f"ping_host exception (default) for {addr}: {e}")

    # try IPv6 explicitly
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

# ---------------------------
# MonitorThread
# ---------------------------
class MonitorThread(QtCore.QThread):
    updated = QtCore.pyqtSignal(str, str, object)  # ip, state, rtt
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
        try:
            entries = list(self.get_entries())
            for e in entries:
                ip = e.get("ip")
                if ip:
                    self.last_state[ip] = None
        except Exception:
            pass

        while self._running:
            entries = list(self.get_entries())
            if not entries:
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
                if prev is None:
                    self.last_state[ip] = ok
                    state = "ONLINE" if ok else "OFFLINE"
                    self.updated.emit(ip, state, rtt)
                elif prev != ok:
                    self.last_state[ip] = ok
                    state = "ONLINE" if ok else "OFFLINE"
                    msg = (
                        f"{'🟢' if ok else '🔴'} {ip} змінив статус:\n"
                        f"Статус: {'ONLINE' if ok else 'OFFLINE'}\n"
                        f"Час: {now_ts()}"
                    )
                    try:
                        write_log(msg)
                        self.log.emit(msg)
                        send_telegram_async(msg)
                    except Exception as ex:
                        write_log(f"Error sending telegram on change: {ex}")
                    self.updated.emit(ip, state, rtt)
                else:
                    state = "ONLINE" if ok else "OFFLINE"
                    self.updated.emit(ip, state, rtt)

                for _ in range(3):
                    if not self._running:
                        break
                    time.sleep(0.02)

            for _ in range(int(self.interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.wait(2000)

# ---------------------------
# Helpers: Icon Button (round)
# ---------------------------
class IconButton(QtWidgets.QToolButton):
    def __init__(self, icon_path: Optional[Path] = None, size: int = 28, tooltip: str = ""):
        super().__init__()
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setAutoRaise(True)
        self.setFixedSize(size+8, size+8)
        if icon_path and icon_path.exists():
            pix = QPixmap(str(icon_path))
            self.setIcon(QIcon(pix))
            self.setIconSize(QtCore.QSize(size, size))
        if tooltip:
            self.setToolTip(tooltip)

# ---------------------------
# UI MainWindow
# ---------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Панель моніторингу — PingMonitor v{CURRENT_VERSION}")
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))
        self.resize(1100, 720)

        # state
        self.cfg = load_config()
        self.group_colors = load_group_colors()
        for g in DEFAULT_GROUPS:
            if g not in self.group_colors:
                self.group_colors[g] = DEFAULT_GROUP_COLORS.get(g, "#DDDDDD")
        save_group_colors(self.group_colors)

        self.monitor_thread: Optional[MonitorThread] = None
        self.status_map: Dict[str, bool] = {}

        # theme state
        self.current_theme = "dark"  # default restored style
        # build UI
        self._build_ui()
        self._load_entries_into_table()

        # prepare thread object
        interval = self.cfg.get("ping_interval", 5)
        timeout = self.cfg.get("ping_timeout", 1)
        self.monitor_thread = MonitorThread(self._get_entries, interval_sec=interval, timeout_s=timeout)
        self.monitor_thread.updated.connect(self._on_update_from_thread)
        self.monitor_thread.log.connect(self._append_log)

        self.apply_dark_theme()
        QtCore.QTimer.singleShot(1200, self.auto_update_check)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_v = QtWidgets.QVBoxLayout(central)
        main_v.setContentsMargins(10, 8, 10, 10)
        main_v.setSpacing(6)

        # Top horizontal: app label + inputs + add/delete + icons (right)
        top_h = QtWidgets.QHBoxLayout()
        top_h.setSpacing(8)

        # App label (left)
        self.label_app = QtWidgets.QLabel(f"<b>PingMonitor</b> — v{CURRENT_VERSION}")
        self.label_app.setObjectName("app_label")
        top_h.addWidget(self.label_app)
        top_h.addSpacing(6)

        # Group combo and IP/note inputs
        self.combo_group = QtWidgets.QComboBox()
        for g in sorted(DEFAULT_GROUPS):
            self.combo_group.addItem(g)
        extra = sorted(set([e.get("group","") for e in self.cfg.get("entries", [])]) - set(DEFAULT_GROUPS))
        for g in extra:
            if g:
                self.combo_group.addItem(g)
        self.input_ip = QtWidgets.QLineEdit(); self.input_ip.setPlaceholderText("IP або hostname")
        self.input_ip.setFixedWidth(320)
        self.input_note = QtWidgets.QLineEdit(); self.input_note.setPlaceholderText("Примітка")
        self.input_note.setFixedWidth(300)

        top_h.addWidget(self.combo_group)
        top_h.addWidget(self.input_ip)
        top_h.addWidget(self.input_note)

        top_h.addStretch()

        # Add / Delete buttons
        self.btn_add = QtWidgets.QPushButton("Додати")
        self.btn_delete = QtWidgets.QPushButton("Видалити")
        self.btn_add.clicked.connect(self.on_add)
        self.btn_delete.clicked.connect(self.on_delete_selected)
        self.btn_add.setObjectName("add")
        self.btn_delete.setObjectName("delete")
        top_h.addWidget(self.btn_add)
        top_h.addWidget(self.btn_delete)

        # Theme & Telegram icons on right
        self.btn_theme_icon = IconButton(DARK_THEME_ICON if self.current_theme=="dark" and DARK_THEME_ICON.exists() else LIGHT_THEME_ICON, size=22, tooltip="Змінити тему")
        self.btn_theme_icon.clicked.connect(self.toggle_theme_icon)
        self.btn_telegram_icon = IconButton(TELEGRAM_ICON if TELEGRAM_ICON.exists() else None, size=22, tooltip="Відкрити Telegram (тест)")
        self.btn_telegram_icon.clicked.connect(self.test_telegram)
        top_h.addWidget(self.btn_theme_icon)
        top_h.addWidget(self.btn_telegram_icon)

        main_v.addLayout(top_h)

        # Search
        self.search_input = QtWidgets.QLineEdit(); self.search_input.setPlaceholderText("Пошук... (IP, примітка, група)")
        self.search_input.textChanged.connect(self.on_search_changed)
        main_v.addWidget(self.search_input)

        # Table (upper of splitter)
        self.table = QtWidgets.QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(["Група","IP-адреса","Примітка","Статус","Пінг (ms)"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setColumnWidth(0,140)
        self.table.setColumnWidth(1,180)
        self.table.setColumnWidth(2,360)
        self.table.setColumnWidth(3,120)
        self.table.setColumnWidth(4,100)

        # Splitter: top = table, bottom = controls+log
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.splitter.addWidget(self.table)

        # Bottom widget contains buttons row + log (we'll allow resizing)
        bottom_widget = QtWidgets.QWidget()
        bottom_v = QtWidgets.QVBoxLayout(bottom_widget)
        bottom_v.setContentsMargins(0,6,0,0)
        bottom_v.setSpacing(8)

        # Buttons row (left) + status (right)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_start = QtWidgets.QPushButton("Запустити моніторинг")
        self.btn_stop = QtWidgets.QPushButton("Зупинити")
        self.btn_clear_log = QtWidgets.QPushButton("Очистити лог")

        self.btn_start.setObjectName("start")
        self.btn_stop.setObjectName("stop")
        self.btn_clear_log.setObjectName("clear")

        self.btn_start.clicked.connect(self.start_monitoring)
        self.btn_stop.clicked.connect(self.stop_monitoring)
        self.btn_clear_log.clicked.connect(self.clear_log)

        self.btn_stop.setEnabled(False)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_clear_log)
        btn_row.addStretch()

        self.label_status = QtWidgets.QLabel("Статус: зупинено")
        btn_row.addWidget(self.label_status)

        bottom_v.addLayout(btn_row)

        # Log
        bottom_v.addWidget(QtWidgets.QLabel("Журнал подій:"))
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(20000)
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    self.log_edit.setPlainText(f.read())
        except Exception:
            pass
        bottom_v.addWidget(self.log_edit, 1)

        self.splitter.addWidget(bottom_widget)
        # set initial sizes: table bigger
        self.splitter.setSizes([420, 220])

        main_v.addWidget(self.splitter, 1)

    # ---------------------------
    # Table helpers
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
    # Actions
    # ---------------------------
    def on_add(self):
        group = self.combo_group.currentText().strip()
        ip = self.input_ip.text().strip()
        note = self.input_note.text().strip()
        if not ip:
            return
        existing = [x for x in self.cfg.setdefault("entries", []) if x.get("ip")==ip and x.get("group")==group]
        if existing:
            QMessageBox.information(self, "Інформація", "Такий IP уже існує в цій групі")
            self.input_ip.clear()
            self.input_note.clear()
            return

        entry = {"group": group, "ip": ip, "note": note}
        self.cfg["entries"].append(entry)
        save_config(self.cfg)
        self._add_table_row(group, ip, note, status="UNKNOWN", ping_ms=None)
        if group not in self.group_colors:
            self.group_colors[group] = DEFAULT_GROUP_COLORS.get(group, "#DDDDDD")
            save_group_colors(self.group_colors)
        write_log(f"Додано {ip} ({note}) в групу {group}")
        self._append_log(f"Додано {ip} ({note}) в групу {group}")
        msg = (f"▶️ До моніторингу додано:\nГрупа: {group}\nIP: {ip}\nПримітка: {note if note else '-'}")
        send_telegram_async(msg)
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
            QMessageBox.warning(self, "Увага", "Додайте хоча б один IP для моніторингу")
            return

        interval = self.cfg.get("ping_interval", 5)
        timeout = self.cfg.get("ping_timeout", 1)
        self.monitor_thread = MonitorThread(self._get_entries, interval_sec=interval, timeout_s=timeout)
        self.monitor_thread.updated.connect(self._on_update_from_thread)
        self.monitor_thread.log.connect(self._append_log)

        send_telegram_async("📡 Моніторинг запущено")
        self._append_log("Моніторинг запущено")

        for e in self.cfg.get("entries", []):
            ip = e.get("ip")
            group = e.get("group","")
            note = e.get("note","")
            try:
                ok, rtt, used = ping_host(ip, timeout_s=timeout)
            except Exception:
                ok, rtt, used = False, None, None
            self.monitor_thread.last_state[ip] = ok
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
            self._on_update_table_row(ip, "ONLINE" if ok else "OFFLINE", rtt)

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
        self._on_update_table_row(ip, state, rtt)

    def _on_update_table_row(self, ip: str, state: str, rtt):
        r = self._find_row_by_ip(ip)
        if r is None:
            group = self.combo_group.currentText() if self.combo_group.currentText() else "Без групи"
            note = ""
            self.cfg.setdefault("entries", []).append({"group": group, "ip": ip, "note": note})
            save_config(self.cfg)
            self._add_table_row(group, ip, note, status=state, ping_ms=rtt)
            return
        status_text = "🟢 ONLINE" if state == "ONLINE" else "🔴 OFFLINE"
        self.table.item(r,3).setText(status_text)
        self.table.item(r,4).setText(str(rtt) if rtt is not None else "-")
        if state == "ONLINE":
            self.table.item(r,3).setForeground(QtGui.QBrush(QtGui.QColor("#00c853")))
        else:
            self.table.item(r,3).setForeground(QtGui.QBrush(QtGui.QColor("#f39c12")))
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
    # Theme toggle
    # ---------------------------
    def toggle_theme_icon(self):
        # toggle theme and swap theme icon
        if self.current_theme == "dark":
            self.apply_light_theme()
            self.current_theme = "light"
            if LIGHT_THEME_ICON.exists():
                self.btn_theme_icon.setIcon(QIcon(str(LIGHT_THEME_ICON)))
        else:
            self.apply_dark_theme()
            self.current_theme = "dark"
            if DARK_THEME_ICON.exists():
                self.btn_theme_icon.setIcon(QIcon(str(DARK_THEME_ICON)))

    def apply_dark_theme(self):
        HOVER_GREEN = "#00ff08"
        HOVER_RED = "#ff0000"
        HOVER_YELLOW = "#fff700"
        self.setStyleSheet(f"""
            QWidget {{ background-color: #2e2f31; color: #e6e6e6; font-family: 'Segoe UI'; font-size: 11pt; }}
            QTableWidget {{ background-color: #323435; color: #e6e6e6; gridline-color: #3b3b3b; }}
            QHeaderView::section {{ background-color: #2f3032; color: #cfcfcf; padding:6px; border:1px solid #3b3b3b; }}
            QLabel#app_label {{ font-size: 12pt; color: #f0f0f0; }}
            QLineEdit {{ background-color: #2f3032; color: #e6e6e6; border:1px solid #3b3b3b; padding:6px; border-radius:6px; }}
            QComboBox {{ background-color: #2f3032; color: #e6e6e6; border:1px solid #3b3b3b; padding:6px; border-radius:6px; }}
            QPlainTextEdit {{ background-color: #292a2b; color: #e6e6e6; border:1px solid #3b3b3b; border-radius:6px; padding:8px; }}
            QPushButton {{ background: transparent; color: #e6e6e6; border:2px solid rgba(255,255,255,0.05); padding:6px 12px; border-radius:6px; }}
            QPushButton#add {{ border-color: rgba(0,255,8,0.28); }}
            QPushButton#add:hover {{ border-color: {HOVER_GREEN}; color: #ffffff; }}
            QPushButton#start {{ border-color: rgba(0,255,8,0.28); }}
            QPushButton#start:hover {{ border-color: {HOVER_GREEN}; color: #ffffff; }}
            QPushButton#stop {{ border-color: rgba(255,0,0,0.18); }}
            QPushButton#stop:hover {{ border-color: {HOVER_RED}; color: #ffffff; }}
            QPushButton#clear {{ border-color: rgba(255,247,0,0.18); }}
            QPushButton#clear:hover {{ border-color: {HOVER_YELLOW}; color: #ffffff; }}
            QPushButton#delete {{ border-color: rgba(255,0,0,0.12); }}
            QPushButton#delete:hover {{ border-color: {HOVER_RED}; color: #ffffff; }}
            QToolButton {{ background: transparent; border: none; padding:2px; }}
        """)
        # ensure text in buttons stays white on hover by style
        for btn in [self.btn_start, self.btn_stop, self.btn_clear_log, self.btn_add, self.btn_delete]:
            btn.setStyleSheet("QPushButton { color: #e6e6e6; } QPushButton:hover { color: #ffffff; }")

    def apply_light_theme(self):
        HOVER_GREEN = "#00ff08"
        HOVER_RED = "#ff0000"
        HOVER_YELLOW = "#fff700"
        self.setStyleSheet(f"""
            QWidget {{ background-color: #f6f8f7; color: #071312; font-family: 'Segoe UI'; font-size: 11pt; }}
            QTableWidget {{ background-color: #ffffff; color: #071312; gridline-color: #ddd; }}
            QHeaderView::section {{ background-color: #eef6ee; color: #1f6a1f; padding:6px; border:1px solid #ddd; }}
            QLabel#app_label {{ font-size: 12pt; color: #071312; }}
            QLineEdit {{ background-color: #ffffff; color: #071312; border:1px solid #ddd; padding:6px; border-radius:6px; }}
            QComboBox {{ background-color: #ffffff; color: #071312; border:1px solid #ddd; padding:6px; border-radius:6px; }}
            QPlainTextEdit {{ background-color: #ffffff; color: #071312; border:1px solid #ddd; border-radius:6px; padding:8px; }}
            QPushButton {{ background: transparent; color: #071312; border:2px solid rgba(0,0,0,0.08); padding:6px 12px; border-radius:6px; }}
            QPushButton#add {{ border-color: rgba(0,255,8,0.18); }}
            QPushButton#add:hover {{ border-color: {HOVER_GREEN}; color: #000000; }}
            QPushButton#start {{ border-color: rgba(0,255,8,0.18); }}
            QPushButton#start:hover {{ border-color: {HOVER_GREEN}; color: #000000; }}
            QPushButton#stop {{ border-color: rgba(255,0,0,0.12); }}
            QPushButton#stop:hover {{ border-color: {HOVER_RED}; color: #000000; }}
            QPushButton#clear {{ border-color: rgba(255,247,0,0.12); }}
            QPushButton#clear:hover {{ border-color: {HOVER_YELLOW}; color: #000000; }}
            QPushButton#delete {{ border-color: rgba(255,0,0,0.12); }}
            QPushButton#delete:hover {{ border-color: {HOVER_RED}; color: #000000; }}
            QToolButton {{ background: transparent; border: none; padding:2px; }}
        """)
        for btn in [self.btn_start, self.btn_stop, self.btn_clear_log, self.btn_add, self.btn_delete]:
            btn.setStyleSheet("QPushButton { color: inherit; } QPushButton:hover { color: inherit; }")

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
    # Auto-update (simple check)
    # ---------------------------
    def auto_update_check(self):
        try:
            response = requests.get(UPDATE_JSON_URL, timeout=5)
            response.raise_for_status()
            data = response.json()
            latest = data.get("version", "")
            url = data.get("download_url", "")
            changelog = data.get("changelog", "")
            if latest and url and latest != CURRENT_VERSION:
                dlg = QMessageBox(self)
                dlg.setWindowTitle("Доступне оновлення")
                dlg.setText(f"Доступна нова версія {latest}.\n\nЗміни:\n{changelog}\n\nЗавантажити та встановити?")
                dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if dlg.exec() == QMessageBox.StandardButton.Yes:
                    path = self._download_update(url)
                    if path:
                        QMessageBox.information(self, "Оновлення", "Файл завантажено. Інсталятор буде запущено.")
                        try:
                            os.startfile(path)
                        except Exception:
                            subprocess.Popen([path], shell=True)
                        QtCore.QCoreApplication.quit()
        except Exception as e:
            write_log(f"auto_update_check error: {e}")

    def _download_update(self, url: str) -> Optional[str]:
        try:
            temp_dir = Path(tempfile.gettempdir())
            filename = url.split("/")[-1]
            out_path = temp_dir / filename
            r = requests.get(url, stream=True, timeout=10)
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return str(out_path)
        except Exception as e:
            write_log(f"Download update error: {e}")
            return None

# ---------------------------
# Entry point
# ---------------------------
def main():
    ensure_default_config()
    app = QtWidgets.QApplication(sys.argv)
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
