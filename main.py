import os
import re
import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
import shutil
from datetime import datetime

# ---------- Настройки CustomTkinter ----------
ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("blue")  

# ---------- Пути ----------
if getattr(sys, "frozen", False):
    APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MyDB")
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(APP_DIR, exist_ok=True)
DB_PATH = os.path.join(APP_DIR, "data.db")

# ---------- Словарь типов данных ----------
TYPE_MAP = {
    "Текст": "TEXT",
    "Целое число": "INTEGER",
    "Дробное число": "REAL",
    "Дата": "DATE"
}

# ---------- Валидация (ТЕПЕРЬ С РУССКИМИ БУКВАМИ) ----------
# Разрешаем английские, русские буквы, цифры, пробелы и нижнее подчеркивание. 
# Начинаться должно с буквы.
NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_ ]{0,49}$")
RESERVED = {"select","from","where","table","index","order","group","by","date","id","primary","key","insert","update","delete","create","drop","alter","and","or","not","null","integer","text","real","default","unique","check"}

def validate_name(name: str):
    if not NAME_RE.match(name):
        return False, "Имя должно начинаться с буквы (русской или английской), содержать только буквы, цифры, пробелы и _, до 50 символов."
    if name.lower() in RESERVED:
        return False, "Это имя зарезервировано системой (например, date, id, select)"
    return True, ""

def q(name: str) -> str:
    # Оборачиваем имя в кавычки для базы данных, экранируя внутренние кавычки
    return '"' + name.replace('"', '""') + '"'

# ---------- Всплывающая подсказка (ToolTip) ----------
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25

        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#ffffe0", relief="solid", borderwidth=1,
                         font=("Segoe UI", 9))
        label.pack(ipadx=5, ipady=5)

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# ---------- Работа с БД ----------
def connect(): return sqlite3.connect(DB_PATH)
def get_tables(conn): return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
def get_columns(conn, table): return conn.execute(f"PRAGMA table_info({q(table)})").fetchall()

def create_table(conn, name, fields):
    cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for fn, ft in fields: cols.append(f"{q(fn)} {ft}")
    cols.append("record_date TEXT DEFAULT (datetime('now','localtime'))")
    conn.execute(f"CREATE TABLE {q(name)} ({', '.join(cols)})")
    conn.commit()

def add_column(conn, table, name, coltype):
    conn.execute(f"ALTER TABLE {q(table)} ADD COLUMN {q(name)} {coltype}")
    conn.commit()

def drop_column(conn, table, name):
    conn.execute(f"ALTER TABLE {q(table)} DROP COLUMN {q(name)}")
    conn.commit()

def drop_table(conn, table):
    conn.execute(f"DROP TABLE {q(table)}")
    conn.commit()

def fetch_rows(conn, table): return conn.execute(f"SELECT * FROM {q(table)} ORDER BY id DESC").fetchall()

def insert_row(conn, table, data):
    cols = list(data.keys())
    ph = ", ".join("?" * len(cols))
    conn.execute(f"INSERT INTO {q(table)} ({', '.join(q(c) for c in cols)}) VALUES ({ph})", [data[c] for c in cols])
    conn.commit()

def update_row(conn, table, row_id, data):
    cols = list(data.keys())
    sets = ", ".join(f"{q(c)} = ?" for c in cols)
    conn.execute(f"UPDATE {q(table)} SET {sets} WHERE id = ?", [data[c] for c in cols] + [row_id])
    conn.commit()

def delete_row(conn, table, row_id):
    conn.execute(f"DELETE FROM {q(table)} WHERE id = ?", [row_id])
    conn.commit()

# ---------- Диалог создания таблицы ----------
class CreateTableDialog(ctk.CTkToplevel):
    def __init__(self, master, conn):
        super().__init__(master)
        self.conn = conn
        self.title("Создать таблицу")
        self.geometry("550x500")
        self.transient(master)
        self.grab_set()
        self.field_rows = []

        ctk.CTkLabel(self, text="Имя таблицы:", font=("Segoe UI", 12)).pack(anchor="w", padx=20, pady=(20, 5))
        self.name_var = ctk.StringVar()
        ctk.CTkEntry(self, textvariable=self.name_var).pack(fill="x", padx=20)

        ctk.CTkLabel(self, text="Поля (имя + тип):", font=("Segoe UI", 12)).pack(anchor="w", padx=20, pady=(15, 5))
        self.fields_frame = ctk.CTkScrollableFrame(self, height=200)
        self.fields_frame.pack(fill="both", expand=True, padx=20)

        ctk.CTkButton(self, text="+ Добавить поле", fg_color="gray", command=self.add_field_row).pack(pady=10)
        ctk.CTkButton(self, text="Создать таблицу", command=self.create).pack(pady=(0, 20), fill="x", padx=20)

        self.add_field_row()

    def add_field_row(self):
        frame = ctk.CTkFrame(self.fields_frame)
        frame.pack(fill="x", pady=5)
        
        name_var = ctk.StringVar()
        ctk.CTkEntry(frame, textvariable=name_var, width=200, placeholder_text="Имя поля").pack(side="left", padx=(5, 10))
        
        type_var = ctk.StringVar(value="Текст")
        combo = ctk.CTkComboBox(frame, variable=type_var, values=list(TYPE_MAP.keys()), width=130, state="readonly")
        combo.pack(side="left")
        
        info_lbl = ctk.CTkLabel(frame, text="❓", text_color="#f39c12", font=("Segoe UI", 16), cursor="hand2")
        info_lbl.pack(side="left", padx=5)
        ToolTip(info_lbl, "Текст: обычные буквы (имена, адреса)\n"
                          "Целое число: 1, 10, 500 (без запятых)\n"
                          "Дробное число: 1.5, 10.99\n"
                          "Дата: 2024-12-31 (ГГГГ-ММ-ДД)")
        
        ctk.CTkButton(frame, text="X", width=30, fg_color="#e74c3c", hover_color="#c0392b", 
                      command=lambda: self.remove_row(frame)).pack(side="left", padx=5)
        
        self.field_rows.append((frame, name_var, type_var))

    def remove_row(self, frame):
        self.field_rows = [r for r in self.field_rows if r[0] is not frame]
        frame.destroy()

    def create(self):
        name = self.name_var.get().strip()
        ok, msg = validate_name(name)
        if not ok:
            messagebox.showerror("Ошибка", msg); return
        if name in get_tables(self.conn):
            messagebox.showerror("Ошибка", "Таблица уже существует"); return

        fields, seen = [], set()
        for _, nv, tv in self.field_rows:
            fn = nv.get().strip()
            if not fn: continue
            ok, msg = validate_name(fn)
            if not ok:
                messagebox.showerror("Ошибка", f"Поле '{fn}': {msg}"); return
            if fn.lower() in seen:
                messagebox.showerror("Ошибка", f"Поле '{fn}' повторяется"); return
            seen.add(fn.lower())
            
            sql_type = TYPE_MAP[tv.get()]
            fields.append((fn, sql_type))
        
        if not fields:
            messagebox.showerror("Ошибка", "Добавьте хотя бы одно поле"); return

        try: create_table(self.conn, name, fields)
        except Exception as e:
            messagebox.showerror("Ошибка БД", str(e)); return
        self.destroy()

# ---------- Диалог записи ----------
class RecordDialog(ctk.CTkToplevel):
    def __init__(self, master, conn, table, columns, row=None):
        super().__init__(master)
        self.conn = conn
        self.table = table
        self.row = row
        self.row_id = row["id"] if row else None
        self.entries = {}

        self.title("Редактировать" if row else "Новая запись")
        self.geometry("450x400")
        self.transient(master)
        self.grab_set()

        scroll_frame = ctk.CTkScrollableFrame(self)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        editable = [c for c in columns if c[1] not in ("id", "record_date")]
        for i, col in enumerate(editable):
            name, ctype = col[1], (col[2] or "TEXT")
            ctk.CTkLabel(scroll_frame, text=name).grid(row=i, column=0, sticky="w", padx=10, pady=5)
            var = ctk.StringVar(value="" if not row or row.get(name) is None else str(row.get(name)))
            ctk.CTkEntry(scroll_frame, textvariable=var, width=250).grid(row=i, column=1, padx=10, pady=5)
            self.entries[name] = (var, ctype)

        ctk.CTkButton(self, text="Сохранить", command=self.save).pack(pady=10, padx=20, fill="x")

    def save(self):
        data = {}
        for name, (var, ctype) in self.entries.items():
            v = var.get()
            t = ctype.upper()
            if t == "INTEGER":
                try: v = int(v) if v != "" else None
                except ValueError: messagebox.showerror("Ошибка", f"{name}: нужно целое число"); return
            elif t == "REAL":
                try: v = float(v) if v != "" else None
                except ValueError: messagebox.showerror("Ошибка", f"{name}: нужно число"); return
            data[name] = v
        try:
            if self.row_id is None: insert_row(self.conn, self.table, data)
            else: update_row(self.conn, self.table, self.row_id, data)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e)); return
        self.destroy()

# ---------- Главное окно ----------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.conn = connect()
        self.current_table = None

        self.title("Моя База Данных")
        self.geometry("1100x700")

        # Левая панель
        self.left_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.left_frame.pack(side="left", fill="y")
        
        ctk.CTkLabel(self.left_frame, text="Таблицы", font=("Segoe UI", 16, "bold")).pack(pady=(20, 10))
        
        self.tables_list = tk.Listbox(self.left_frame, exportselection=False, font=("Segoe UI", 11), 
                                      bg="#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#ffffff", 
                                      fg="white" if ctk.get_appearance_mode() == "Dark" else "black",
                                      selectbackground="#1f538d", borderwidth=0, highlightthickness=0)
        self.tables_list.pack(fill="both", expand=True, padx=15, pady=5)
        self.tables_list.bind("<<ListboxSelect>>", self.on_table_select)

        ctk.CTkButton(self.left_frame, text="Создать таблицу", command=self.create_table).pack(fill="x", padx=15, pady=(5, 2))
        ctk.CTkButton(self.left_frame, text="Добавить поле", fg_color="gray", command=self.add_field).pack(fill="x", padx=15, pady=2)
        ctk.CTkButton(self.left_frame, text="Удалить поле", fg_color="gray", command=self.drop_field).pack(fill="x", padx=15, pady=2)
        ctk.CTkButton(self.left_frame, text="Удалить таблицу", fg_color="#e74c3c", hover_color="#c0392b", command=self.drop_table).pack(fill="x", padx=15, pady=2)
        ctk.CTkButton(self.left_frame, text="Резервная копия", fg_color="#f39c12", hover_color="#d68910", command=self.backup).pack(fill="x", padx=15, pady=(20, 20))

        # Правая панель (Данные)
        self.right_frame = ctk.CTkFrame(self, corner_radius=0)
        self.right_frame.pack(side="right", fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        
        self.tree = ttk.Treeview(self.right_frame, show="headings")
        self.tree.pack(fill="both", expand=True, padx=15, pady=15)
        
        self.tree.tag_configure('oddrow', background='#f0f0f0')
        self.tree.tag_configure('evenrow', background='#ffffff')

        bf = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        bf.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkButton(bf, text="Добавить запись", command=self.add_record).pack(side="left", padx=5)
        ctk.CTkButton(bf, text="Изменить", fg_color="#3498db", hover_color="#2980b9", command=self.edit_record).pack(side="left", padx=5)
        ctk.CTkButton(bf, text="Удалить", fg_color="#e74c3c", hover_color="#c0392b", command=self.delete_record).pack(side="left", padx=5)
        ctk.CTkButton(bf, text="Обновить", fg_color="gray", command=self.refresh_records).pack(side="left", padx=15)

        self.tree.bind("<Double-1>", lambda e: self.edit_record())

        self.refresh_tables()

    def refresh_tables(self):
        self.tables_list.delete(0, "end")
        for t in get_tables(self.conn): self.tables_list.insert("end", t)

    def on_table_select(self, _e=None):
        sel = self.tables_list.curselection()
        if not sel: return
        self.current_table = self.tables_list.get(sel[0])
        self.refresh_records()

    def create_table(self):
        dlg = CreateTableDialog(self, self.conn)
        self.wait_window(dlg)
        self.refresh_tables()

    def add_field(self):
        if not self.current_table:
            messagebox.showinfo("Внимание", "Сначала выберите таблицу слева"); return
        name = ctk.CTkInputDialog(text="Имя поля:", title="Новое поле").get_input()
        if not name: return
        ok, msg = validate_name(name.strip())
        if not ok: messagebox.showerror("Ошибка", msg); return
        
        coltype = ctk.CTkInputDialog(text="Тип (Текст, Целое число, Дробное число, Дата):", title="Тип поля").get_input()
        if coltype not in TYPE_MAP:
            messagebox.showerror("Ошибка", "Недопустимый тип. Введите: Текст, Целое число, Дробное число или Дата."); return
        
        try: add_column(self.conn, self.current_table, name.strip(), TYPE_MAP[coltype])
        except Exception as e: messagebox.showerror("Ошибка", str(e)); return
        self.refresh_records()

    def drop_field(self):
        if not self.current_table: return
        cols = [c[1] for c in get_columns(self.conn, self.current_table) if c[1] not in ("id", "record_date")]
        if not cols: return
        name = ctk.CTkInputDialog(text="Введите имя поля для удаления:\n" + ", ".join(cols), title="Удалить поле").get_input()
        if name not in cols: return
        if not messagebox.askyesno("Подтверждение", f"Удалить поле '{name}' и все данные в нём?"): return
        try: drop_column(self.conn, self.current_table, name)
        except Exception as e: messagebox.showerror("Ошибка", str(e)); return
        self.refresh_records()

    def drop_table(self):
        if not self.current_table: return
        if not messagebox.askyesno("Подтверждение", f"Удалить таблицу '{self.current_table}' со всеми данными?"): return
        drop_table(self.conn, self.current_table)
        self.current_table = None
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = ()
        self.refresh_tables()

    def refresh_records(self):
        self.tree.delete(*self.tree.get_children())
        if not self.current_table: return
        cols = get_columns(self.conn, self.current_table)
        names = [c[1] for c in cols]
        self.tree["columns"] = names
        for n in names:
            self.tree.heading(n, text=n)
            self.tree.column(n, width=120, anchor="w")
        
        for i, row in enumerate(fetch_rows(self.conn, self.current_table)):
            tag = 'evenrow' if i % 2 == 0 else 'oddrow'
            self.tree.insert("", "end", iid=str(row[0]), values=row, tags=(tag,))

    def add_record(self):
        if not self.current_table:
            messagebox.showinfo("Внимание", "Сначала выберите таблицу слева"); return
        cols = get_columns(self.conn, self.current_table)
        dlg = RecordDialog(self, self.conn, self.current_table, cols)
        self.wait_window(dlg)
        self.refresh_records()

    def edit_record(self):
        sel = self.tree.selection()
        if not sel or not self.current_table: return
        row_id = int(sel[0])
        cols = get_columns(self.conn, self.current_table)
        row = self.conn.execute(f"SELECT * FROM {q(self.current_table)} WHERE id = ?", (row_id,)).fetchone()
        row_dict = {c[1]: v for c, v in zip(cols, row)}
        dlg = RecordDialog(self, self.conn, self.current_table, cols, row=row_dict)
        self.wait_window(dlg)
        self.refresh_records()

    def delete_record(self):
        sel = self.tree.selection()
        if not sel or not self.current_table: return
        if not messagebox.askyesno("Подтверждение", "Удалить выбранную запись?"): return
        delete_row(self.conn, self.current_table, int(sel[0]))
        self.refresh_records()

    def backup(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        default_name = f"backup_{timestamp}.db"
        filepath = filedialog.asksaveasfilename(title="Сохранить резервную копию", initialfile=default_name, defaultextension=".db", filetypes=[("База данных SQLite", "*.db")])
        if filepath:
            try:
                self.conn.commit()
                shutil.copy2(DB_PATH, filepath)
                messagebox.showinfo("Успех", "Резервная копия успешно сохранена!")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить копию:\n{e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()