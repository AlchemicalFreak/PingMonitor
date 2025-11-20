#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PingMonitor v1.0.2
- UI: theme icon + telegram icon top-right
- Buttons: dim default borders, bright on hover per user colors
- Clear log placed right of Stop
- Removed title above IP field
- Auto-update via version.json
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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMessageBox, QApplication

# ---------------------------
# Configs
# ---------------------------
TELEGRAM_TOKEN = "8446791342:AAFo1iHvk6dmquwtr3AJ2BcD-9mIxUzCC00"
CHAT_ID = "-1003368463307"

CURRENT_VERSION = "1.0.2"
UPDATE_JSON_URL = "https://raw.githubusercontent.com/AlchemicalFreak/PingMonitor/main/version.json"

# Paths
APPDATA_ENV = os.getenv("APPDATA")
if APPDATA_ENV:
    APP_DIR = Path(APPDATA_ENV) / "PingMonitor"
else:
    APP_DIR = Path.home() / ".pingmonitor"
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DIR / "config.json"
GROUP_COLORS_FILE = APP_DIR / "group_colors.json"
LOG_FILE = APP_DIR / "monitor.log"
BASE_DIR = Path(__file__).parent
ICON_FILE = BASE_DIR / "icon.ico"
TELEGRAM_ICON = BASE_DIR / "telegram.ico"
LIGHT_THEME_ICON = BASE_DIR / "lighttheme.ico"
DARK_THEME_ICON = BASE_DIR / "darktheme.ico"

# Defaults
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

# Hover colors requested
HOVER_GREEN = "#00ff08"
HOVER_YELLOW = "#fff700"
HOVER_RED = "#ff0000"

# ---------------------------
# Utilities
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
    except Exception:
        cfg = {"entries": [], "ping_interval": 5, "ping_timeout": 1}
    return cfg

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
    except Exception:
        pass
    save_group_colors(DEFAULT_GROUP_COLORS)
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
# Ping helper
# ---------------------------
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
            return True, elapsed_ms, addr
    except Exception as e:
        write_log(f"ping default exception: {e}")

    # Try IPv6
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
            return True, elapsed6, addr
    except Exception as e:
        write_log(f"ping ipv6 exception: {e}")

    return False, None, None

# ---------------------------
# Monitor Thread
# ---------------------------
class MonitorThread(QtCore.QThread):
    updated = QtCore.pyqtSignal(str, str, object)
    log = QtCore.pyqtSignal(str)

    def __init__(self, get_entries_callable, interval_sec: float = 5.0, timeout_s: float = 1.0):
        super().__init__()
        self.get_entries = get_entries_callable
        self.interval = interval_sec
        self.timeout = timeout_s
        self._running = False
        self.last_state = {}

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
                    if not self._running: break
                    time.sleep(0.1)
                continue

            for e in entries:
                if not self._running: break
                ip = e.get("ip")
                if not ip: continue
                try:
                    ok, rtt, used = ping_host(ip, timeout_s=self.timeout)
                except Exception as ex:
                    ok, rtt, used = False, None, None
                    write_log(f"ping error {ip}: {ex}")

                prev = self.last_state.get(ip)
                if prev is None:
                    self.last_state[ip] = ok
                    state = "ONLINE" if ok else "OFFLINE"
                    self.updated.emit(ip, state, rtt)
                elif prev != ok:
                    self.last_state[ip] = ok
                    state = "ONLINE" if ok else "OFFLINE"
                    msg = (f"{'🟢' if ok else '🔴'} {ip} змінив статус:\n"
                           f"Статус: {'ONLINE' if ok else 'OFFLINE'}\nЧас: {now_ts()}")
                    try:
                        write_log(msg)
                        self.log.emit(msg)
                        send_telegram_async(msg)
                    except Exception as ex:
                        write_log(f"send telegram on change error: {ex}")
                    self.updated.emit(ip, state, rtt)
                else:
                    state = "ONLINE" if ok else "OFFLINE"
                    self.updated.emit(ip, state, rtt)

                for _ in range(3):
                    if not self._running: break
                    time.sleep(0.02)

            for _ in range(int(self.interval * 10)):
                if not self._running: break
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.wait(2000)

# ---------------------------
# MainWindow
# ---------------------------
class IconButton(QtWidgets.QToolButton):
    def __init__(self, icon_path: Path, size: int = 28):
        super().__init__()
        self.setIcon(QIcon(str(icon_path)) if icon_path.exists() else QIcon())
        self.setIconSize(QtCore.QSize(size, size))
        self.setAutoRaise(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        # style will be applied by parent stylesheet

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_theme = "dark"  # initialize before UI build
        self.setWindowIcon(QIcon(str(ICON_FILE)) if ICON_FILE.exists() else QIcon())
        self.resize(1024, 680)
        self.setWindowTitle("PingMonitor v1.0.2")

        # state
        self.cfg = load_config()
        self.group_colors = load_group_colors()
        for g in DEFAULT_GROUPS:
            if g not in self.group_colors:
                self.group_colors[g] = DEFAULT_GROUP_COLORS.get(g, "#DDDDDD")
        save_group_colors(self.group_colors)

        self.monitor_thread = None
        self.status_map = {}

        # UI
        self._build_ui()
        self._load_entries_into_table()

        # prepare thread (not started)
        interval = self.cfg.get("ping_interval", 5)
        timeout = self.cfg.get("ping_timeout", 1)
        self.monitor_thread = MonitorThread(self._get_entries, interval_sec=interval, timeout_s=timeout)
        self.monitor_thread.updated.connect(self._on_update_from_thread)
        self.monitor_thread.log.connect(self._append_log)

        # apply theme
        self.apply_dark_theme()

        # auto update check shortly after start
        QtCore.QTimer.singleShot(1500, self.auto_update_check)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(10,10,10,10)
        v.setSpacing(8)

        # Top row: left fields + right icons
        top_row = QtWidgets.QHBoxLayout()
        # left: group combo, ip, note, add, delete
        left = QtWidgets.QHBoxLayout()
        self.combo_group = QtWidgets.QComboBox()
        for g in sorted(DEFAULT_GROUPS):
            self.combo_group.addItem(g)
        extra = sorted(set([e.get("group","") for e in self.cfg.get("entries", [])]) - set(DEFAULT_GROUPS))
        for g in extra:
            if g: self.combo_group.addItem(g)

        self.input_ip = QtWidgets.QLineEdit(); self.input_ip.setPlaceholderText("IP або hostname")
        self.input_ip.setFixedWidth(300)
        self.input_note = QtWidgets.QLineEdit(); self.input_note.setPlaceholderText("Примітка")
        self.input_note.setFixedWidth(300)

        self.btn_add = QtWidgets.QPushButton("Додати"); self.btn_add.setObjectName("add")
        self.btn_delete = QtWidgets.QPushButton("Видалити"); self.btn_delete.setObjectName("delete")
        self.btn_add.clicked.connect(self.on_add)
        self.btn_delete.clicked.connect(self.on_delete_selected)

        left.addWidget(self.combo_group)
        left.addWidget(self.input_ip)
        left.addWidget(self.input_note)
        left.addWidget(self.btn_add)
        left.addWidget(self.btn_delete)
        left.addStretch()

        top_row.addLayout(left)

        # right: theme icon + telegram icon
        right = QtWidgets.QHBoxLayout()
        right.setSpacing(6)
        right.setContentsMargins(0,0,0,0)
        # theme icon (shows opposite icon depending on current theme)
        theme_icon_path = DARK_THEME_ICON if self.current_theme == "dark" else LIGHT_THEME_ICON
        self.btn_theme_icon = IconButton(theme_icon_path, size=26)
        self.btn_theme_icon.clicked.connect(self._on_theme_icon_clicked)
        self.btn_theme_icon.setObjectName("themeIcon")
        # telegram icon
        self.btn_telegram_icon = IconButton(TELEGRAM_ICON if TELEGRAM_ICON.exists() else Path(""), size=26)
        self.btn_telegram_icon.clicked.connect(lambda: send_telegram_async("🔔 Тест від PingMonitor: " + now_ts()))
        self.btn_telegram_icon.setObjectName("telegramIcon")

        right.addWidget(self.btn_theme_icon)
        right.addWidget(self.btn_telegram_icon)
        top_row.addLayout(right)
        v.addLayout(top_row)

        # search row
        search_row = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit(); self.search_input.setPlaceholderText("Пошук... (IP, примітка, група)")
        self.search_input.textChanged.connect(self.on_search_changed)
        search_row.addWidget(self.search_input)
        v.addLayout(search_row)

        # === TABLE ===
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

        # === BOTTOM BLOCK (BUTTONS + LOG) ===
        bottom = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0,0,0,0)

        # Buttons row
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Запустити моніторинг"); self.btn_start.setObjectName("start")
        self.btn_stop = QtWidgets.QPushButton("Зупинити"); self.btn_stop.setObjectName("stop")
        self.btn_clear_log = QtWidgets.QPushButton("Очистити лог"); self.btn_clear_log.setObjectName("clear")

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

        bottom_layout.addLayout(btn_row)

        # Log block
        log_title = QtWidgets.QLabel("Журнал подій:")
        bottom_layout.addWidget(log_title)

        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(10000)

        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    self.log_edit.setPlainText(f.read())
        except:
            pass

        bottom_layout.addWidget(self.log_edit)

        # === SPLITTER ===
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        v.addWidget(splitter)

        # styles: object names used for targeted styles
        self._apply_styles()

    # ---------------------------
    # table helpers
    # ---------------------------
    def _add_table_row(self, group: str, ip: str, note: str, status: str = "UNKNOWN", ping_ms: Optional[int]=None):
        r = self.table.rowCount(); self.table.insertRow(r)
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
        self.table.setItem(r,0,item_group); self.table.setItem(r,1,item_ip)
        self.table.setItem(r,2,item_note); self.table.setItem(r,3,item_status); self.table.setItem(r,4,item_ping)

    def _find_row_by_ip(self, ip: str) -> Optional[int]:
        for r in range(self.table.rowCount()):
            it = self.table.item(r,1)
            if it and it.text() == ip:
                return r
        return None

    def _load_entries_into_table(self):
        self.table.setRowCount(0)
        for e in self.cfg.get("entries", []):
            self._add_table_row(e.get("group",""), e.get("ip",""), e.get("note",""), status="UNKNOWN", ping_ms=None)

    def _get_entries(self):
        return list(self.cfg.get("entries", []))

    # ---------------------------
    # actions: add / delete
    # ---------------------------
    def on_add(self):
        group = self.combo_group.currentText().strip()
        ip = self.input_ip.text().strip()
        note = self.input_note.text().strip()
        if not ip:
            return
        existing = [x for x in self.cfg.setdefault("entries", []) if x.get("ip")==ip and x.get("group")==group]
        if existing:
            QtWidgets.QMessageBox.information(self, "Інформація", "Такий IP уже існує в цій групі")
            self.input_ip.clear(); self.input_note.clear(); return
        entry = {"group": group, "ip": ip, "note": note}
        self.cfg["entries"].append(entry); save_config(self.cfg)
        self._add_table_row(group, ip, note, status="UNKNOWN", ping_ms=None)
        if group not in self.group_colors:
            self.group_colors[group] = DEFAULT_GROUP_COLORS.get(group, "#DDDDDD"); save_group_colors(self.group_colors)
        write_log(f"Додано {ip} ({note}) в групу {group}"); self._append_log(f"Додано {ip} ({note}) в групу {group}")
        msg = (f"▶️ До моніторингу додано:\nГрупа: {group}\nIP: {ip}\nПримітка: {note if note else '-'}")
        send_telegram_async(msg)
        self.input_ip.clear(); self.input_note.clear()

    def on_delete_selected(self):
        rows = sorted([idx.row() for idx in self.table.selectionModel().selectedRows()], reverse=True)
        if not rows: return
        for r in rows:
            ip_item = self.table.item(r,1); note_item = self.table.item(r,2); group_item = self.table.item(r,0)
            ip = ip_item.text() if ip_item else ""; note = note_item.text() if note_item else ""; group = group_item.text() if group_item else ""
            self.cfg["entries"] = [x for x in self.cfg.get("entries", []) if not (x.get("ip")==ip and x.get("group")==group)]
            self.table.removeRow(r)
            write_log(f"Видалено {ip} ({note}) з групи {group}"); self._append_log(f"Видалено {ip} ({note}) з групи {group}")
            self.status_map.pop(ip, None)
            if self.monitor_thread and ip in self.monitor_thread.last_state:
                self.monitor_thread.last_state.pop(ip, None)
        save_config(self.cfg)

    # ---------------------------
    # search/filter
    # ---------------------------
    def on_search_changed(self, text: str):
        t = text.lower().strip()
        for r in range(self.table.rowCount()):
            visible = False
            for c in range(self.table.columnCount()):
                it = self.table.item(r,c)
                if it and t in it.text().lower():
                    visible = True; break
            self.table.setRowHidden(r, not visible)

    # ---------------------------
    # monitoring control
    # ---------------------------
    def start_monitoring(self):
        if not self.cfg.get("entries"):
            QtWidgets.QMessageBox.warning(self, "Увага", "Додайте хоча б один IP для моніторингу"); return
        interval = self.cfg.get("ping_interval", 5); timeout = self.cfg.get("ping_timeout", 1)
        self.monitor_thread = MonitorThread(self._get_entries, interval_sec=interval, timeout_s=timeout)
        self.monitor_thread.updated.connect(self._on_update_from_thread); self.monitor_thread.log.connect(self._append_log)
        send_telegram_async("📡 Моніторинг запущено"); self._append_log("Моніторинг запущено")
        for e in self.cfg.get("entries", []):
            ip = e.get("ip"); group = e.get("group",""); note = e.get("note","")
            try:
                ok, rtt, used = ping_host(ip, timeout_s=timeout)
            except Exception:
                ok, rtt, used = False, None, None
            self.monitor_thread.last_state[ip] = ok
            status_emoji = "🟢" if ok else "🔴"
            msg = (f"{status_emoji} Почато моніторинг:\nГрупа: {group}\nIP: {ip}\nПримітка: {note if note else '-'}\nСтатус: {'ONLINE' if ok else 'OFFLINE'}")
            if ok and rtt is not None: msg += f" ({rtt} ms)"
            send_telegram_async(msg)
            self._on_update_table_row(ip, "ONLINE" if ok else "OFFLINE", rtt)
        self.monitor_thread.start()
        self.btn_start.setEnabled(False); self.btn_stop.setEnabled(True); self.label_status.setText("Статус: моніторинг запущено")
        write_log("Моніторинг запущено")

    def stop_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
        self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False); self.label_status.setText("Статус: зупинено")
        self._append_log("Моніторинг зупинено"); write_log("Моніторинг зупинено")

    # ---------------------------
    # updates from thread
    # ---------------------------
    def _on_update_from_thread(self, ip: str, state: str, rtt):
        self._on_update_table_row(ip, state, rtt)

    def _on_update_table_row(self, ip: str, state: str, rtt):
        r = self._find_row_by_ip(ip)
        if r is None:
            group = self.combo_group.currentText() or "Без групи"; note = ""
            self.cfg.setdefault("entries", []).append({"group": group, "ip": ip, "note": note}); save_config(self.cfg)
            self._add_table_row(group, ip, note, status=state, ping_ms=rtt); return
        status_text = "🟢 ONLINE" if state == "ONLINE" else "🔴 OFFLINE"
        self.table.item(r,3).setText(status_text); self.table.item(r,4).setText(str(rtt) if rtt is not None else "-")
        if state == "ONLINE":
            self.table.item(r,3).setForeground(QtGui.QBrush(QtGui.QColor("#00c853")))
        else:
            self.table.item(r,3).setForeground(QtGui.QBrush(QtGui.QColor("#f39c12")))
        self.status_map[ip] = (state == "ONLINE")

    # ---------------------------
    # log UI
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
    # theme toggle
    # ---------------------------
    def _on_theme_icon_clicked(self):
        # toggle theme and update icon
        if self.current_theme == "dark":
            self.apply_light_theme(); self.current_theme = "light"
            if LIGHT_THEME_ICON.exists(): self.btn_theme_icon.setIcon(QIcon(str(LIGHT_THEME_ICON)))
        else:
            self.apply_dark_theme(); self.current_theme = "dark"
            if DARK_THEME_ICON.exists(): self.btn_theme_icon.setIcon(QIcon(str(DARK_THEME_ICON)))

    def apply_dark_theme(self):
        self.current_theme = "dark"
        self.setStyleSheet(f"""
            QWidget {{ background-color: #2e2f30; color: #e6e7e8; font-family: 'Segoe UI'; }}
            QTableWidget {{ background-color: #333536; color: #e6e7e8; gridline-color: #3b3b3b; }}
            QHeaderView::section {{ background-color: #38393a; color: #d7e6dd; }}
            QLineEdit {{ background-color: #2f3132; color: #ddd; border:1px solid #3a3a3a; padding:6px; border-radius:6px; }}
            QPlainTextEdit {{ background-color: #2b2c2d; color: #e6e7e8; border:1px solid #3a3a3a; border-radius:6px; padding:8px; }}
            /* Buttons default: dimmed borders (darker versions), bright on hover */
            QPushButton#start {{
                background: transparent; color: #e6e7e8; border:2px solid rgba(0,255,8,0.25); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#start:hover {{ border-color: {HOVER_GREEN}; box-shadow: none; }}
            QPushButton#add {{
                background: transparent; color:#e6e7e8; border:2px solid rgba(0,255,8,0.25); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#add:hover {{ border-color: {HOVER_GREEN}; }}
            QPushButton#stop {{
                background: transparent; color:#e6e7e8; border:2px solid rgba(255,0,0,0.18); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#stop:hover {{ border-color: {HOVER_RED}; }}
            QPushButton#clear {{
                background: transparent; color:#e6e7e8; border:2px solid rgba(255,247,0,0.18); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#clear:hover {{ border-color: {HOVER_YELLOW}; }}
            QPushButton#delete {{
                background: transparent; color:#e6e7e8; border:2px solid rgba(255,0,0,0.2); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#delete:hover {{ border-color: {HOVER_RED}; }}
            /* Icon buttons in top-right */
            QToolButton#themeIcon, QToolButton#telegramIcon {{
                background: transparent; border:2px solid rgba(255,255,255,0.06); border-radius:14px; padding:4px;
            }}
            QToolButton#themeIcon:hover, QToolButton#telegramIcon:hover {{
                border-color: rgba(255,255,255,0.2);
                filter: brightness(1.15);
            }}
        """)
        # refresh icons depending on theme
        if DARK_THEME_ICON.exists():
            self.btn_theme_icon.setIcon(QIcon(str(DARK_THEME_ICON)))

    def apply_light_theme(self):
        self.current_theme = "light"
        self.setStyleSheet(f"""
            QWidget {{ background-color: #f2f2f2; color: #0b0b0b; font-family: 'Segoe UI'; }}
            QTableWidget {{ background-color: #ffffff; color: #0b0b0b; gridline-color: #ddd; }}
            QHeaderView::section {{ background-color: #f0f0f0; color: #2b2b2b; }}
            QLineEdit {{ background-color: #ffffff; color: #0b0b0b; border:1px solid #d0d0d0; padding:6px; border-radius:6px; }}
            QPlainTextEdit {{ background-color: #ffffff; color: #0b0b0b; border:1px solid #d0d0d0; border-radius:6px; padding:8px; }}
            QPushButton#start {{
                background: transparent; color: #0b0b0b; border:2px solid rgba(0,255,8,0.18); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#start:hover {{ border-color: {HOVER_GREEN}; }}
            QPushButton#add {{
                background: transparent; color:#0b0b0b; border:2px solid rgba(0,255,8,0.18); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#add:hover {{ border-color: {HOVER_GREEN}; }}
            QPushButton#stop {{
                background: transparent; color:#0b0b0b; border:2px solid rgba(255,0,0,0.18); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#stop:hover {{ border-color: {HOVER_RED}; }}
            QPushButton#clear {{
                background: transparent; color:#0b0b0b; border:2px solid rgba(255,247,0,0.18); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#clear:hover {{ border-color: {HOVER_YELLOW}; }}
            QPushButton#delete {{
                background: transparent; color:#0b0b0b; border:2px solid rgba(255,0,0,0.16); padding:6px 12px; border-radius:6px;
            }}
            QPushButton#delete:hover {{ border-color: {HOVER_RED}; }}
            QToolButton#themeIcon, QToolButton#telegramIcon {{
                background: transparent; border:2px solid rgba(0,0,0,0.06); border-radius:14px; padding:4px;
            }}
            QToolButton#themeIcon:hover, QToolButton#telegramIcon:hover {{
                border-color: rgba(0,0,0,0.18);
                filter: brightness(1.08);
            }}
        """)
        if LIGHT_THEME_ICON.exists():
            self.btn_theme_icon.setIcon(QIcon(str(LIGHT_THEME_ICON)))

    def _apply_styles(self):
        # Called at UI build: ensure icons reflect theme
        if self.current_theme == "dark":
            if DARK_THEME_ICON.exists(): self.btn_theme_icon.setIcon(QIcon(str(DARK_THEME_ICON)))
        else:
            if LIGHT_THEME_ICON.exists(): self.btn_theme_icon.setIcon(QIcon(str(LIGHT_THEME_ICON)))

    # ---------------------------
    # Auto-update helpers
    # ---------------------------
    def auto_update_check(self):
        try:
            upd = check_for_updates()
            if not upd: return
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

def is_newer_version(v1: str, v2: str) -> bool:
    try:
        a = [int(x) for x in v1.split(".")]
        b = [int(x) for x in v2.split(".")]
        return a > b
    except Exception:
        return v1 != v2 and v1 > v2

def check_for_updates():
    try:
        r = requests.get(UPDATE_JSON_URL, timeout=6)
        r.raise_for_status()
        data = r.json()
        latest = data.get("version", "")
        url = data.get("download_url", "")
        changelog = data.get("changelog", "")
        if latest and url and is_newer_version(latest, CURRENT_VERSION):
            return latest, url, changelog
    except Exception as e:
        write_log(f"Update check failed: {e}")
    return None

def download_update(url: str) -> Optional[str]:
    try:
        temp_dir = Path(tempfile.gettempdir())
        filename = url.split("/")[-1]
        out_path = temp_dir / filename
        write_log(f"Downloading update to {out_path}")
        r = requests.get(url, stream=True, timeout=15); r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        write_log("Update downloaded successfully")
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
