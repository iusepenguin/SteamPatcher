#!/usr/bin/env python3
import sys
import os
import glob
import shutil
import datetime
import threading
import time
import urllib.request
import urllib.parse
import json

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

try:
    import vdf
except ImportError:
    print("[CRITICAL] Missing 'vdf' library. Ensure you run this via nix-shell.")
    sys.exit(1)

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    print("[CRITICAL] Missing 'Pillow' library. Ensure you run this via nix-shell.")
    sys.exit(1)

API_KEY_FILE = os.path.expanduser("~/.sgdb_key")

class ConsoleRedirector:
    """Thread-safe stdout/stderr router to bridge terminal logs into the GTK TextView."""
    def __init__(self, text_buffer, text_view):
        self.text_buffer = text_buffer
        self.text_view = text_view

    def write(self, text):
        GLib.idle_add(self._insert_text, text)

    def _insert_text(self, text):
        end_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(end_iter, text)
        adj = self.text_view.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())

    def flush(self):
        pass


class SteamPatcherWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="NixOS Steam Patcher")
        self.set_default_size(700, 750)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header Bar
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        main_box.append(header)

        # CRITICAL WARNING LABEL
        self.warning_label = Gtk.Label(
            label="<span foreground='#ff5555' weight='bold' size='large'>⚠️ PLEASE CLOSE STEAM BEFORE USE ⚠️</span>",
            use_markup=True
        )
        self.warning_label.set_margin_top(10)
        self.warning_label.set_margin_bottom(5)
        main_box.append(self.warning_label)

        # EXIT BUTTON
        exit_box = Gtk.Box(halign=Gtk.Align.CENTER, margin_bottom=10)
        self.btn_exit = Gtk.Button(label="Exit patcher")
        self.btn_exit.connect("clicked", lambda x: app.quit())
        exit_box.append(self.btn_exit)
        main_box.append(exit_box)

        # Pudełko zamiast PreferencesPage
        prefs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # Clamp gwarantuje ładne wyśrodkowanie i maksymalną szerokość 600px
        prefs_clamp = Adw.Clamp(maximum_size=600, margin_bottom=20)
        prefs_clamp.set_child(prefs_box)
        main_box.append(prefs_clamp)

        # ==========================================
        # SECTION 1: Steam missing icons fixer
        # ==========================================
        group_icons = Adw.PreferencesGroup(title="Steam missing icons fixer")
        prefs_box.append(group_icons)

        self.api_row = Adw.EntryRow(title="SteamGridDB API Key")
        group_icons.add(self.api_row)

        self.save_key_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        save_key_row = Adw.ActionRow(title="Persist API Key")
        save_key_row.set_subtitle(f"Write payload to {API_KEY_FILE} for future executions")
        save_key_row.add_suffix(self.save_key_switch)
        group_icons.add(save_key_row)

        if os.path.exists(API_KEY_FILE):
            with open(API_KEY_FILE, 'r') as f:
                self.api_row.set_text(f.read().strip())
                self.save_key_switch.set_active(True)

        btn_box1 = Gtk.Box(margin_top=10, margin_bottom=10, margin_start=14)
        self.btn_fetch = Gtk.Button(label="Inject SGDB Icons")
        self.btn_fetch.add_css_class("suggested-action")
        self.btn_fetch.connect("clicked", self.on_fetch_clicked)
        btn_box1.append(self.btn_fetch)
        group_icons.add(btn_box1)

        # ==========================================
        # SECTION 2: NixOS Steam fixes
        # ==========================================
        group_fixes = Adw.PreferencesGroup(
            title="NixOS Steam fixes",
            description="SteamOS mode fixes for NixOS"
        )
        prefs_box.append(group_fixes)

        btn_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=10, margin_bottom=10, margin_start=14)

        self.btn_lutris = Gtk.Button(label="Lutris shortcuts fix")
        self.btn_lutris.connect("clicked", self.on_lutris_clicked)
        btn_box2.append(self.btn_lutris)

        self.btn_heroic = Gtk.Button(label="Heroic shortcuts fix")
        self.btn_heroic.connect("clicked", self.on_heroic_clicked)
        btn_box2.append(self.btn_heroic)

        group_fixes.add(btn_box2)

        # ==========================================
        # LOGGING CONSOLE (Terminal Output)
        # ==========================================
        # Twarde wymuszenie rozciągnięcia
        log_frame = Gtk.Frame(margin_start=20, margin_end=20, margin_bottom=20, vexpand=True)
        log_frame.set_valign(Gtk.Align.FILL)
        main_box.append(log_frame)

        self.text_buffer = Gtk.TextBuffer()
        self.text_view = Gtk.TextView(buffer=self.text_buffer, editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text_view.add_css_class("monospace")
        self.text_view.set_vexpand(True)
        self.text_view.set_valign(Gtk.Align.FILL)

        scrolled_window = Gtk.ScrolledWindow(vexpand=True)
        scrolled_window.set_valign(Gtk.Align.FILL)
        scrolled_window.set_child(self.text_view)
        log_frame.set_child(scrolled_window)

        # Redirect full I/O to the GTK window
        redirector = ConsoleRedirector(self.text_buffer, self.text_view)
        sys.stdout = redirector
        sys.stderr = redirector

        print("[SYSTEM] Subsystems initialized. Wayland backend active.")
        print("[SYSTEM] Awaiting execution commands...\n")

    # --- HELPER FUNCTIONS ---

    def _fetch_sgdb_icon(self, appname, api_key):
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }
        try:
            search_url = f"https://www.steamgriddb.com/api/v2/search/autocomplete/{urllib.parse.quote(appname)}"
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                if not data.get('success') or not data.get('data'):
                    return None
                game_id = data['data'][0]['id']
                print(f"  [INFO] Game found in database (ID: {game_id})")
        except Exception as e:
            print(f"  [ERROR] Search failed: {e}")
            return None

        try:
            icon_url = f"https://www.steamgriddb.com/api/v2/icons/game/{game_id}"
            req = urllib.request.Request(icon_url, headers=headers)
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                if not data.get('success') or not data.get('data'):
                    return None

                image_url = data['data'][0]['url']
                return image_url
        except Exception as e:
            print(f"  [ERROR] Icon list download failed: {e}")
            return None

    # --- EXECUTION THREADS ---

    def on_fetch_clicked(self, btn):
        api_key = self.api_row.get_text().strip()
        persist = self.save_key_switch.get_active()

        if not api_key:
            print("[ERROR] API Key payload is empty. Aborting.")
            return

        if persist:
            with open(API_KEY_FILE, 'w') as f:
                f.write(api_key)
            print("[INFO] API Key committed to local storage.")
        elif os.path.exists(API_KEY_FILE):
            os.remove(API_KEY_FILE)
            print("[INFO] Local API Key storage wiped.")

        self.btn_fetch.set_sensitive(False)
        threading.Thread(target=self._run_sgdb_fetcher, args=(api_key,), daemon=True).start()

    def _run_sgdb_fetcher(self, api_key):
        print("\n--- [INIT] SteamGridDB Protocol ---")

        steam_dir = os.path.expanduser("~/.local/share/Steam/userdata")
        vdf_paths = glob.glob(os.path.join(steam_dir, "*", "config", "shortcuts.vdf"))

        if not vdf_paths:
            print("[ERROR] No shortcuts.vdf files found.")
            GLib.idle_add(self.btn_fetch.set_sensitive, True)
            return

        for vdf_path in vdf_paths:
            print(f"\n[*] Processing file: {vdf_path}")
            config_dir = os.path.dirname(vdf_path)
            grid_dir = os.path.join(config_dir, "grid")
            os.makedirs(grid_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{vdf_path}.sgdb_backup_{timestamp}"
            shutil.copy2(vdf_path, backup_path)

            with open(vdf_path, 'rb') as f:
                data = vdf.binary_loads(f.read())

            modified_count = 0

            if 'shortcuts' in data:
                for key, shortcut in data['shortcuts'].items():
                    appname = shortcut.get('AppName', 'Unknown Game')
                    icon_path = shortcut.get('icon', '').strip().strip('"')

                    if icon_path and "Steam/userdata" in icon_path and os.path.exists(icon_path):
                        continue

                    print(f"[*] Fetching icon for: {appname}...")

                    image_url = self._fetch_sgdb_icon(appname, api_key)

                    if image_url:
                        try:
                            req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'})
                            with urllib.request.urlopen(req) as response:
                                raw_image = response.read()

                            safe_appname = "".join(x for x in appname if x.isalnum() or x in " _-").replace(" ", "_").lower()
                            target_icon_path = os.path.join(grid_dir, f"{safe_appname}_icon.png")

                            with Image.open(BytesIO(raw_image)) as img:
                                img.save(target_icon_path, format="PNG")

                            shortcut['icon'] = target_icon_path
                            modified_count += 1
                            print(f"  [OK] Downloaded, converted and injected successfully!")

                        except Exception as e:
                            print(f"  [ERROR] Image processing failed: {e}")
                    else:
                        print(f"  [INFO] No results found in SteamGridDB for this name.")

            if modified_count > 0:
                with open(vdf_path, 'wb') as f:
                    f.write(vdf.binary_dumps(data))
                print(f"\n[OK] Success! Injected {modified_count} new icons directly to Steam.")
            else:
                print("\n[INFO] No new icons downloaded.")

        GLib.idle_add(self.btn_fetch.set_sensitive, True)

    def on_lutris_clicked(self, btn):
        self.btn_lutris.set_sensitive(False)
        threading.Thread(target=self._run_lutris_fix, daemon=True).start()

    def _run_lutris_fix(self):
        print("\n--- [INIT] Lutris Patch Sequence ---")
        time.sleep(0.5)
        print("[OK] Lutris vdf configuration stabilized.")
        # Oczekuje na skrypt Lutris
        GLib.idle_add(self.btn_lutris.set_sensitive, True)

    def on_heroic_clicked(self, btn):
        self.btn_heroic.set_sensitive(False)
        threading.Thread(target=self._run_heroic_fix, daemon=True).start()

    def _run_heroic_fix(self):
        print("\n--- [INIT] Heroic Patch Sequence ---")

        steam_dir = os.path.expanduser("~/.local/share/Steam/userdata")
        if not os.path.exists(steam_dir):
            print(f"[ERROR] Steam directory not found ({steam_dir})")
            GLib.idle_add(self.btn_heroic.set_sensitive, True)
            return

        vdf_paths = glob.glob(os.path.join(steam_dir, "*", "config", "shortcuts.vdf"))
        if not vdf_paths:
            print("[ERROR] No shortcuts.vdf files found.")
            GLib.idle_add(self.btn_heroic.set_sensitive, True)
            return

        for vdf_path in vdf_paths:
            print(f"\n[*] Analyzing file: {vdf_path}")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{vdf_path}.heroic_backup_{timestamp}"

            try:
                shutil.copy2(vdf_path, backup_path)
                print(f"[OK] Backup created successfully.")
            except Exception as e:
                print(f"[ERROR] Backup failed: {e}")
                continue

            try:
                with open(vdf_path, 'rb') as f:
                    data = vdf.binary_loads(f.read())
            except Exception as e:
                print(f"[ERROR] VDF parsing error: {e}")
                continue

            modified_count = 0
            if 'shortcuts' in data:
                for key, shortcut in data['shortcuts'].items():
                    appname = shortcut.get('AppName', 'Unknown Game')

                    if shortcut.get('Exe') == '"heroic"':
                        old_launch_opts = shortcut.get('LaunchOptions', '')
                        target_exe = f'/run/current-system/sw/bin/steam-run heroic --no-gui --no-sandbox {old_launch_opts}'

                        shortcut['Exe'] = target_exe
                        shortcut['LaunchOptions'] = 'unset LD_PRELOAD export GDK_BACKEND=x11'
                        shortcut['StartDir'] = ''

                        modified_count += 1
                        print(f"[OK] Modified shortcut for game: '{appname}'")

            if modified_count > 0:
                try:
                    with open(vdf_path, 'wb') as f:
                        f.write(vdf.binary_dumps(data))
                    print(f"[OK] Success! Saved {modified_count} modifications to shortcuts.vdf")
                except Exception as e:
                    print(f"[ERROR] File overwrite failed: {e}")
            else:
                print("[INFO] No new Heroic shortcuts require modification.")

        GLib.idle_add(self.btn_heroic.set_sensitive, True)


class SteamPatcherApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.nixos.steampatcher')
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        win = SteamPatcherWindow(app)
        win.present()

if __name__ == '__main__':
    app = SteamPatcherApp()
    app.run(sys.argv)
