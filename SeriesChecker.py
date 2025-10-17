import sqlite3
import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
import requests, zipfile, io, os, sys, threading, time

UPDATE_BASE_URL = "https://raw.githubusercontent.com//sutsujepet/SeriesChecker/main"

def safe_update_status(text):
    if update_status and update_status.winfo_exists():
        update_status.config(text=text)

def check_for_updates():
    try:
        version_url = f"{UPDATE_BASE_URL}/version.txt"
        data_url = f"{UPDATE_BASE_URL}/data.zip"
        local_version_path = os.path.join("data", "local_version.txt")

        # 🔹 Determine local version
        LOCAL_VERSION = None
        if os.path.exists(local_version_path):
            try:
                with open(local_version_path, "r", encoding="utf-8") as f:
                    LOCAL_VERSION = f.read().strip()
            except Exception:
                LOCAL_VERSION = None

        # 🔹 Load initial data if no local version exists
        if not LOCAL_VERSION:
            root.after(0, lambda: safe_update_status("⬇️ Loading initial data..."))
            r = requests.get(data_url, timeout=30)
            r.raise_for_status()
            if os.path.exists("data"):
                import shutil
                shutil.rmtree("data", ignore_errors=True)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall("data")

            online_version = requests.get(version_url, timeout=5).text.strip()
            os.makedirs("data", exist_ok=True)
            with open(local_version_path, "w", encoding="utf-8") as f:
                f.write(online_version)
            root.after(0, lambda: safe_update_status(f"✅ Initial data loaded (v{online_version})"))
            return

        # 🔹 Check online version
        online_version = requests.get(version_url, timeout=5).text.strip()
        if online_version != LOCAL_VERSION:
            root.after(0, lambda: safe_update_status(f"🆕 New version {online_version} – updating..."))

            # Save license state
            owned_cars, owned_tracks = set(), set()
            if os.path.exists(CARS_DB):
                conn = sqlite3.connect(CARS_DB)
                cur = conn.cursor()
                cur.execute("SELECT name FROM cars WHERE licensed = 1")
                owned_cars = {r[0] for r in cur.fetchall()}
                conn.close()
            if os.path.exists(TRACKS_DB):
                conn = sqlite3.connect(TRACKS_DB)
                cur = conn.cursor()
                cur.execute("SELECT name FROM tracks WHERE licensed = 1")
                owned_tracks = {r[0] for r in cur.fetchall()}
                conn.close()

            # Download and extract new data package
            r = requests.get(data_url, timeout=30)
            r.raise_for_status()
            import shutil
            if os.path.exists("data"):
                shutil.rmtree("data", ignore_errors=True)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall("data")

            # Restore license state
            if os.path.exists("data/cars.db"):
                conn = sqlite3.connect("data/cars.db")
                cur = conn.cursor()
                for n in owned_cars:
                    cur.execute("UPDATE cars SET licensed = 1 WHERE name = ?", (n,))
                conn.commit()
                conn.close()
            if os.path.exists("data/tracks.db"):
                conn = sqlite3.connect("data/tracks.db")
                cur = conn.cursor()
                for n in owned_tracks:
                    cur.execute("UPDATE tracks SET licensed = 1 WHERE name = ?", (n,))
                conn.commit()
                conn.close()

            with open(local_version_path, "w", encoding="utf-8") as f:
                f.write(online_version)
            root.after(0, lambda: safe_update_status(f"✅ Update completed (v{online_version})"))
        else:
            root.after(0, lambda: safe_update_status("✅ Data is up to date."))
    except Exception as e:
        root.after(0, lambda: safe_update_status(f"⚠️ Update failed: {e}"))

def resource_path(relative_path):
    """Return absolute path to resource (works in .exe too)"""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    if relative_path.startswith("data"):
        base_path = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.path.abspath(".")
    return os.path.join(base_path, relative_path)

CARS_DB = resource_path("data/cars.db")
TRACKS_DB = resource_path("data/tracks.db")
SCHEDULE_DB = resource_path("data/schedule.db")

CURRENT_PAGE = 0

FILTER_STATE = {
    "category": "All",
    "class": "All",
    "series": "All",
    "car": "All",
    "week": "All",
    "active": False
}

root = tb.Window(themename="darkly")
root.overrideredirect(True)
root.configure(bg="#1a1a1a")

splash_w, splash_h = 520, 520
screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()
pos_x = int((screen_w - splash_w) / 2)
pos_y = int((screen_h - splash_h) / 2)
root.geometry(f"{splash_w}x{splash_h}+{pos_x}+{pos_y}")

try:
    icon_path = resource_path("data/icon.ico")
    icon_img = Image.open(icon_path)
    icon_img = icon_img.resize((512, 512))
    icon_tk = ImageTk.PhotoImage(icon_img)
    splash_label = tk.Label(root, image=icon_tk, bg="#1a1a1a")
    splash_label.place(relx=0.5, rely=0.5, anchor="center")
    root.icon_ref = icon_tk
except Exception:
    tk.Label(root, text="iRacing Planner", font=("Segoe UI", 26, "bold"), fg="white", bg="#1a1a1a").place(relx=0.5, rely=0.5, anchor="center")

def show_main_window():
    root.overrideredirect(False)
    root.geometry("")
    root.state("zoomed")
    root.configure(bg="#1a1a1a")
    for widget in root.winfo_children():
        widget.destroy()
    show_main_menu()

root.after(4000, show_main_window)

ACCENT_COLOR = "#E63946"
BG_COLOR = "#1a1a1a"
root.configure(bg=BG_COLOR)

# Update status label
update_status = tb.Label(root, text="🔍 Checking for updates...", font=("Segoe UI", 10), background=BG_COLOR)

# --- Utility functions ---
def get_licensed_names(db_path, table):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT name FROM {table} WHERE licensed = 1")
    names = [row[0] for row in cursor.fetchall()]
    conn.close()
    return names

def analyze_schedule():
    car_conn = sqlite3.connect(CARS_DB)
    c_cursor = car_conn.cursor()
    c_cursor.execute("SELECT name FROM cars WHERE licensed = 1")
    licensed_cars = {row[0] for row in c_cursor.fetchall()}
    car_conn.close()

    track_conn = sqlite3.connect(TRACKS_DB)
    t_cursor = track_conn.cursor()
    t_cursor.execute("SELECT name FROM tracks WHERE licensed = 1")
    licensed_tracks = {row[0] for row in t_cursor.fetchall()}
    track_conn.close()

    conn = sqlite3.connect(SCHEDULE_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    result = []
    for table in tables:
        cursor.execute(f"SELECT cars, track FROM {table}")
        rows = cursor.fetchall()
        all_cars_in_series = {row[0] for row in rows if row[0]}
        has_any_car = any(car in licensed_cars for car in all_cars_in_series)

        if not has_any_car:
            continue

        driveable_weeks = []
        for week_index, (car_name, track_name) in enumerate(rows, start=1):
            if track_name in licensed_tracks:
                driveable_weeks.append(week_index)

        if driveable_weeks:
            result.append((table, driveable_weeks))

    conn.close()
    result.sort(key=lambda x: len(x[1]), reverse=True)
    return result

def clear_window():
    for widget in root.winfo_children():
        widget.destroy()

def show_series_list():
    clear_window()
    root.title("Plan Series")

    tb.Label(root, text="Series Planner", font=("Segoe UI", 18, "bold")).pack(pady=15)

    full_series_data = analyze_schedule()
    filtered_data = full_series_data.copy()

    filter_frame = tb.Frame(root)
    filter_frame.pack(fill="x", pady=5)

    selected_category = tk.StringVar(value=FILTER_STATE["category"])
    selected_class = tk.StringVar(value=FILTER_STATE["class"])
    selected_series = tk.StringVar(value=FILTER_STATE["series"])
    selected_car = tk.StringVar(value=FILTER_STATE["car"])
    selected_week = tk.StringVar(value=FILTER_STATE["week"])

    tb.Label(filter_frame, text="Category:").grid(row=0, column=0, padx=5)
    category_box = tb.Combobox(filter_frame, textvariable=selected_category,
        values=["All", "OVAL", "SPORTS CAR", "FORMULA CAR", "DIRT OVAL", "DIRT ROAD", "UNRANKED"], state="readonly", width=15)
    category_box.grid(row=0, column=1, padx=5)

    tb.Label(filter_frame, text="License:").grid(row=0, column=2, padx=5)
    class_box = tb.Combobox(filter_frame, textvariable=selected_class,
        values=["All", "R", "D", "C", "B", "A", "Pro"], state="readonly", width=7)
    class_box.grid(row=0, column=3, padx=5)

    tb.Label(filter_frame, text="Series:").grid(row=0, column=4, padx=5)
    series_names = ["All"] + [name for name, _ in full_series_data]
    series_box = tb.Combobox(filter_frame, textvariable=selected_series, values=series_names, state="readonly", width=25)
    series_box.grid(row=0, column=5, padx=5)

    tb.Label(filter_frame, text="Car:").grid(row=0, column=6, padx=5)
    car_conn = sqlite3.connect(CARS_DB)
    c_cursor = car_conn.cursor()
    c_cursor.execute("SELECT name FROM cars ORDER BY name")
    all_cars = ["All"] + [row[0] for row in c_cursor.fetchall()]
    car_conn.close()
    car_box = tb.Combobox(filter_frame, textvariable=selected_car, values=all_cars, state="readonly", width=20)
    car_box.grid(row=0, column=7, padx=5)

    tb.Label(filter_frame, text="Week:").grid(row=0, column=8, padx=5)
    week_box = tb.Combobox(filter_frame, textvariable=selected_week, values=["All"] + [str(i) for i in range(1, 13)], state="readonly", width=5)
    week_box.grid(row=0, column=9, padx=5)

    def reset_filters():
        selected_category.set("All")
        selected_class.set("All")
        selected_series.set("All")
        selected_car.set("All")
        selected_week.set("All")
        filtered_data[:] = full_series_data
        update_list()
        for key in FILTER_STATE:
            FILTER_STATE[key] = "All"
        FILTER_STATE["active"] = False

    tb.Button(filter_frame, text="Reset", bootstyle='secondary', command=reset_filters).grid(row=0, column=10, padx=10)

    container = tb.Frame(root)
    container.pack(fill="both", expand=True, padx=10, pady=5)

    canvas = tk.Canvas(container, highlightthickness=0, bg=BG_COLOR)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = tb.Frame(canvas)

    window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def save_filter_state():
        FILTER_STATE.update({
            "category": selected_category.get(),
            "class": selected_class.get(),
            "series": selected_series.get(),
            "car": selected_car.get(),
            "week": selected_week.get(),
            "active": True
        })

    def update_list():
        global CURRENT_PAGE
        for widget in container.winfo_children():
            widget.destroy()

        if not filtered_data:
            tb.Label(container, text="Keine fahrbaren Serien gefunden.", bootstyle="danger").pack(pady=20)
            return

        max_width_chars = max(len(f"{series_name}  ({len(weeks)} Wochen)") for series_name, weeks in filtered_data)
        button_width = max_width_chars + 2
        max_rows_per_column = 20
        total_columns = (len(filtered_data) + max_rows_per_column - 1) // max_rows_per_column

        columns_per_page = 3
        total_pages = (total_columns + columns_per_page - 1) // columns_per_page

        current_page = min(CURRENT_PAGE, total_pages - 1)
        start_col = current_page * columns_per_page
        end_col = min(start_col + columns_per_page, total_columns)

        columns_frame = tb.Frame(container)
        columns_frame.pack(expand=True)

        for col_idx in range(start_col, end_col):
            col_frame = tb.Frame(columns_frame)
            col_frame.pack(side="left", padx=20)

            for row in range(max_rows_per_column):
                idx = col_idx * max_rows_per_column + row
                if idx >= len(filtered_data):
                    break
                series_name, weeks = filtered_data[idx]
                tb.Button(
                    col_frame,
                    text=f"{series_name}  ({len(weeks)} Wochen)",
                    width=button_width,
                    bootstyle="danger",
                    padding=(10, 5),
                    command=lambda s=series_name, w=weeks: (save_filter_state(), show_series_detail(s, w))
                ).pack(pady=5, fill="x")

        if total_pages > 1:
            page_frame = tb.Frame(container)
            page_frame.pack(pady=10)
            for p in range(total_pages):
                style = 'primary' if p == current_page else 'secondary'
                tb.Button(page_frame, text=str(p+1), bootstyle=style,
                        command=lambda p=p: (set_page(p), update_list())).pack(side="left", padx=5)

    def set_page(page):
        global CURRENT_PAGE
        CURRENT_PAGE = page

    def apply_filters():
        nonlocal filtered_data
        filtered_data = []

        for series_name, weeks in full_series_data:
            include = True
            conn = sqlite3.connect(SCHEDULE_DB)
            cur = conn.cursor()

            cur.execute(f"SELECT class FROM '{series_name}' WHERE class IS NOT NULL LIMIT 1")
            row = cur.fetchone()
            series_class = row[0] if row else ""

            cur.execute(f"SELECT license FROM '{series_name}' WHERE license IS NOT NULL LIMIT 1")
            row = cur.fetchone()
            series_license = row[0] if row else ""

            if selected_category.get() != "All" and (not series_class or selected_category.get().lower() not in series_class.lower()):
                include = False

            if selected_class.get() != "All" and (not series_license or selected_class.get().upper() != series_license.upper()):
                include = False

            if selected_series.get() != "All" and selected_series.get().lower() not in series_name.lower():
                include = False

            if selected_week.get() != "All":
                try:
                    week_num = int(selected_week.get())
                    if week_num not in weeks:
                        include = False
                except ValueError:
                    pass

            if selected_car.get() != "All":
                cur.execute(f"SELECT cars FROM '{series_name}' WHERE cars IS NOT NULL")
                rows = cur.fetchall()
                all_cars_in_series = set()
                for row in rows:
                    if row[0]:
                        for car in row[0].splitlines():
                            all_cars_in_series.add(car.strip())
                if not any(selected_car.get().lower() in c.lower() for c in all_cars_in_series):
                    include = False

            conn.close()

            if include:
                filtered_data.append((series_name, weeks))

        update_list()

    tb.Button(filter_frame, text="Apply Filters", bootstyle='danger', command=apply_filters).grid(row=0, column=11, padx=5)
    tb.Button(root, text="⬅ Back", bootstyle='secondary', command=show_main_menu).pack(side="bottom", pady=10)

    if FILTER_STATE["active"]:
        apply_filters()

def show_series_detail(series_name, weeks):
    clear_window()
    tb.Label(root, text=f"{series_name} – Fahrbare Wochen", font=("Segoe UI", 16, "bold"), bootstyle="danger").pack(pady=10)
    container = tb.Frame(root)
    container.pack(fill="both", expand=True, padx=20, pady=10)
    container.columnconfigure(0, weight=1)

    conn = sqlite3.connect(SCHEDULE_DB)
    cursor = conn.cursor()
    cursor.execute(f"SELECT rowid, cars, track FROM '{series_name}'")
    all_weeks = {rowid: (cars, track) for rowid, cars, track in cursor.fetchall()}
    conn.close()

    licensed_cars = set(get_licensed_names(CARS_DB, "cars"))
    licensed_tracks = set(get_licensed_names(TRACKS_DB, "tracks"))

    weeks_display = []
    series_cars_all = set()

    for w, (cars_str, track_name) in all_weeks.items():
        cars_in_week = set()
        if cars_str:
            cars_in_week = {c.strip() for c in cars_str.splitlines() if c.strip()}
            series_cars_all.update(cars_in_week)
        if track_name and track_name in licensed_tracks:
            weeks_display.append((w, track_name))

    row_idx = 0
    if not weeks_display:
        tb.Label(container, text="❌ Keine fahrbaren Wochen für diese Serie.", bootstyle="danger").grid(row=row_idx, column=0, pady=10)
        row_idx += 1
    else:
        for w, track_name in weeks_display:
            tb.Label(container, text=f"Week {w}: {track_name}", font=("Segoe UI", 11)).grid(row=row_idx, column=0, pady=3)
            row_idx += 1

    tb.Label(container, text="Deine Autos für diese Serie:", font=("Segoe UI", 12, "bold"), bootstyle="danger").grid(row=row_idx, column=0, pady=15)
    row_idx += 1

    licensed_cars_for_series = sorted([c for c in series_cars_all if c in licensed_cars])
    if licensed_cars_for_series:
        for car in licensed_cars_for_series:
            tb.Label(container, text=f"✅ {car}", font=("Segoe UI", 10)).grid(row=row_idx, column=0, pady=3)
            row_idx += 1
    else:
        tb.Label(container, text="❌ Keine passenden Autos lizenziert", bootstyle="danger").grid(row=row_idx, column=0, pady=5)

    tb.Button(root, text="⬅ Back", bootstyle='secondary', command=show_series_list).pack(side="bottom", pady=10)

def show_content_menu():
    clear_window()
    root.title("Select Content")

    tb.Label(root, text="Select Content", font=("Segoe UI", 18, "bold"), bootstyle="danger", background=BG_COLOR).pack(pady=15)

    container = tb.Frame(root)
    container.pack(fill="both", expand=True, padx=10, pady=5)

    save_frame = tb.Frame(root)
    save_frame.pack(pady=10)

    save_button = tb.Button(save_frame, text="Save Selection", bootstyle="success", command=lambda: save_selection())
    save_button.pack(side="left")

    status_label = tb.Label(save_frame, text="", font=("Segoe UI", 10), foreground="#5cb85c", background=BG_COLOR)
    status_label.pack(side="left", padx=10)

    def save_selection():
        # Cars
        conn = sqlite3.connect(CARS_DB)
        cur = conn.cursor()
        for car_id, var in car_vars.items():
            cur.execute("UPDATE cars SET licensed = ? WHERE id = ?", (1 if var.get() else 0, car_id))
        conn.commit()
        conn.close()

        # Tracks
        conn = sqlite3.connect(TRACKS_DB)
        cur = conn.cursor()
        for track_id, var in track_vars.items():
            cur.execute("UPDATE tracks SET licensed = ? WHERE id = ?", (1 if var.get() else 0, track_id))
        conn.commit()
        conn.close()

        status_label.config(text="✅ Saved!")
        save_frame.update_idletasks()


    tb.Button(root, text="⬅ Back", bootstyle="secondary", width=20, command=show_main_menu).pack(side="bottom", pady=10)

    car_vars = {}
    car_conn = sqlite3.connect(CARS_DB)
    c_cursor = car_conn.cursor()
    c_cursor.execute("SELECT id, name, licensed FROM cars ORDER BY name")
    cars = []
    for car_id, car_name, licensed in c_cursor.fetchall():
        var = tk.BooleanVar(value=bool(licensed))
        car_vars[car_id] = var
        cars.append((car_id, car_name))
    car_conn.close()

    track_vars = {}
    track_conn = sqlite3.connect(TRACKS_DB)
    t_cursor = track_conn.cursor()
    t_cursor.execute("SELECT id, name, licensed, price FROM tracks ORDER BY name")
    tracks = []
    for track_id, track_name, licensed, price in t_cursor.fetchall():
        var = tk.BooleanVar(value=bool(licensed))
        track_vars[track_id] = var
        display_name = f"{track_name} ({price})" if price else track_name
        tracks.append((track_id, display_name))
    track_conn.close()

    current_view = tk.StringVar(value="Cars")

    def render_items(items, selected_vars, title=""):
        max_rows_per_column = 20
        total_columns = (len(items) + max_rows_per_column - 1) // max_rows_per_column
        columns_per_page = 3
        total_pages = (total_columns + columns_per_page - 1) // columns_per_page
        current_page = 0

        page_frame_ref = None

        def draw_page(page):
            nonlocal current_page, page_frame_ref
            current_page = page

            for widget in container.winfo_children():
                widget.destroy()

            columns_frame = tb.Frame(container)
            columns_frame.pack(expand=True)

            start_col = page * columns_per_page
            end_col = min(start_col + columns_per_page, total_columns)

            max_width_chars = max(len(name) for _id, name in items)
            button_width = max_width_chars + 2

            for col_idx in range(start_col, end_col):
                col_frame = tb.Frame(columns_frame)
                col_frame.pack(side="left", padx=20)

                for row in range(max_rows_per_column):
                    idx = col_idx * max_rows_per_column + row
                    if idx >= len(items):
                        break
                    _id, name = items[idx]
                    var = selected_vars[_id]
                    tb.Checkbutton(
                        col_frame,
                        text=name,
                        variable=var,
                        bootstyle="success-round-toggle",
                        width=button_width,
                        padding=(5,3)
                    ).pack(pady=3, fill="x")

            if page_frame_ref is not None:
                page_frame_ref.destroy()

            if total_pages > 1 or True:
                page_frame_ref = tb.Frame(container)
                page_frame_ref.pack(pady=10)

                if total_pages > 1:
                    for p in range(total_pages):
                        style = 'primary' if p == current_page else 'secondary'
                        tb.Button(page_frame_ref, text=str(p+1), bootstyle=style,
                                command=lambda p=p: draw_page(p)).pack(side="left", padx=5)

                toggle_text = "Switch to Tracks" if current_view.get() == "Cars" else "Switch to Cars"
                tb.Button(page_frame_ref, text=toggle_text, bootstyle="warning",
                        command=toggle_view).pack(side="left", padx=20)

                reset_text = "Reset to Free Cars" if current_view.get() == "Cars" else "Reset to Free Tracks"
                tb.Button(page_frame_ref, text=reset_text, bootstyle="secondary-outline",
                        command=reset_to_free).pack(side="left", padx=5)

        def reset_to_free():
            if current_view.get() == "Cars":
                conn = sqlite3.connect(CARS_DB)
                cur = conn.cursor()

                cur.execute("UPDATE cars SET licensed = 0")

                cur.execute("UPDATE cars SET licensed = 1 WHERE price IS NULL OR price = '' OR price = 'Free'")
                conn.commit()
                conn.close()

                for car_id in car_vars:
                    car_vars[car_id].set(False)
                cur_list = conn = sqlite3.connect(CARS_DB)
                c = cur_list.cursor()
                c.execute("SELECT id FROM cars WHERE price IS NULL OR price = '' OR price = 'Free'")
                for (cid,) in c.fetchall():
                    if cid in car_vars:
                        car_vars[cid].set(True)
                conn.close()
                render_items(cars, car_vars, title="Cars")

            else:  # Tracks
                conn = sqlite3.connect(TRACKS_DB)
                cur = conn.cursor()
                cur.execute("UPDATE tracks SET licensed = 0")
                cur.execute("UPDATE tracks SET licensed = 1 WHERE price IS NULL OR price = '' OR price = 'Free'")
                conn.commit()
                conn.close()
                for track_id in track_vars:
                    track_vars[track_id].set(False)
                conn = sqlite3.connect(TRACKS_DB)
                c = conn.cursor()
                c.execute("SELECT id FROM tracks WHERE price IS NULL OR price = '' OR price = 'Free'")
                for (tid,) in c.fetchall():
                    if tid in track_vars:
                        track_vars[tid].set(True)
                conn.close()
                render_items(tracks, track_vars, title="Tracks")


        draw_page(0)

    def toggle_view():
        if current_view.get() == "Cars":
            current_view.set("Tracks")
            render_items(tracks, track_vars, title="Tracks")
        else:
            current_view.set("Cars")
            render_items(cars, car_vars, title="Cars")

    render_items(cars, car_vars, title="Cars")


def show_main_menu():
    clear_window()
    root.title("iRacing Planner")

    try:
        logo_img = Image.open("icon.ico")
        screen_w = root.winfo_screenwidth()
        logo_img = logo_img.resize((int(screen_w * 0.8), int(screen_w * 0.25)))
        logo_tk = ImageTk.PhotoImage(logo_img)
        tb.Label(root, image=logo_tk).pack(pady=20)
        root.logo_ref = logo_tk
    except Exception as e:
        tb.Label(root, text="iRacing Planner", font=("Segoe UI", 22, "bold"), bootstyle="danger", background=BG_COLOR).pack(pady=30)

    menu = tb.Frame(root)
    menu.pack(pady=30)

    tb.Button(menu, text="🚗 Select Content", bootstyle='danger-outline', width=24, command=show_content_menu).pack(pady=6)
    tb.Button(menu, text="🏁 Plan Series", bootstyle='danger-outline', width=24, command=show_series_list).pack(pady=6)
    tb.Button(menu, text="❌ Exit", bootstyle='secondary', width=24, command=root.destroy).pack(pady=6)


# Start background update thread
threading.Thread(target=check_for_updates, daemon=True).start()

root.mainloop()
