import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk, Gio, GdkPixbuf, Gdk, GLib, Notify
import os
import re
import json
import shutil
import argparse
import logging
from dateutil import parser as dateparser
from send2trash import send2trash  # Import the send2trash library

class FileManager:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.file_list = []
        self.show_directories = False
        self.show_hidden_files = False
        self.file_type_filter = None

    def load_files(self, liststore):
        self.file_list = []
        liststore.clear()
        for entry in os.scandir(self.folder_path):
            if entry.is_file() or (self.show_directories and entry.is_dir()):
                if not entry.name.startswith('.') or self.show_hidden_files:
                    file_type = self.get_file_type(entry)
                    if self.file_type_filter is None or file_type == self.file_type_filter:
                        self.file_list.append(entry.path)
                        icon = self.get_file_icon(entry.path)
                        liststore.append([False, icon, entry.name, "", file_type, Gdk.RGBA()])

    def get_file_icon(self, file_path):
        file_info = Gio.File.new_for_path(file_path).query_info('standard::icon', Gio.FileQueryInfoFlags.NONE, None)
        icon = file_info.get_icon()
        icon_theme = Gtk.IconTheme.get_default()
        icon_names = icon.get_names()
        try:
            return icon_theme.load_icon(icon_names[0], 16, 0)
        except GLib.Error:
            return icon_theme.load_icon("text-x-generic", 16, 0)  # Fallback to generic text icon

    def get_file_type(self, entry):
        if entry.is_dir():
            return "Directory"
        elif entry.is_file():
            return entry.name.split('.')[-1].upper() if '.' in entry.name else "Unknown"
        return "Unknown"

    def navigate_up(self):
        parent_path = os.path.dirname(self.folder_path)
        self.folder_path = parent_path

    def navigate_to(self, path):
        self.folder_path = path

    def update_path(self, path):
        expanded_path = os.path.abspath(os.path.expanduser(path))
        if os.path.isdir(expanded_path):
            self.folder_path = expanded_path
            return True
        return False

    def set_file_type_filter(self, file_type):
        self.file_type_filter = file_type


class Renamr(Gtk.Window):
    def __init__(self, folder_path=None, config_path=None, verbose_level=logging.INFO):
        super().__init__(title="Renamr")
        self.set_border_width(10)
        self.set_default_size(800, 600)
        self.set_resizable(True)
        self.set_deletable(True)

        # Set application icon
        self.set_icon_from_file("res/application_icon.svg")

        # Set logging level
        logging.basicConfig(level=verbose_level)

        # Enable window decorations (including minimize and maximize buttons)
        self.set_decorated(True)

        # Initialize notifications
        Notify.init("Renamr")

        # Initialize file manager
        self.file_manager = FileManager(folder_path if folder_path else os.path.expanduser("~"))

        # Initialize cut files and copied files
        self.copied_files = []
        self.cut_files = []

        # Initialize undo stack
        self.undo_stack = []

        # Layout container
        main_vbox = Gtk.VBox(spacing=6)
        self.add(main_vbox)

        # Create MenuBar
        self.create_menu_bar()
        main_vbox.pack_start(self.menubar, False, False, 0)

        # Create Paned container for left and right sections
        main_paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        main_vbox.pack_start(main_paned, True, True, 0)

        # Create Grid layout for inputs
        left_vbox = Gtk.VBox(spacing=6)
        self.create_input_grid(left_vbox)
        main_paned.pack1(left_vbox, resize=False, shrink=False)

        # File manager section
        right_vbox = Gtk.VBox(spacing=6)

        # Current directory path box with buttons
        self.create_folder_path_box(right_vbox)

        # Create TreeView for file selection and preview
        self.treeview = Gtk.TreeView()
        self.create_tree_view()

        # Add a ScrolledWindow for the TreeView
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(self.treeview)
        right_vbox.pack_start(scrolled_window, True, True, 0)

        main_paned.pack2(right_vbox, resize=True, shrink=False)

        # Load files from the specified directory by default
        self.folder_path_entry.set_text(self.file_manager.folder_path)
        self.file_manager.load_files(self.liststore)

        # Load configuration if provided
        if config_path:
            self.load_config(config_path)

        # Connect the key press event to the TreeView
        self.treeview.connect("key-press-event", self.on_treeview_key_press)

    def create_menu_bar(self):
        self.menubar = Gtk.MenuBar()

        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem(label="File")
        file_item.set_submenu(file_menu)

        open_folder_item = Gtk.MenuItem(label="Open Folder")
        open_folder_item.connect("activate", self.on_folder_clicked)
        file_menu.append(open_folder_item)

        save_config_item = Gtk.MenuItem(label="Save Configuration")
        save_config_item.connect("activate", self.on_save_config_clicked)
        file_menu.append(save_config_item)

        import_config_item = Gtk.MenuItem(label="Import Configuration")
        import_config_item.connect("activate", self.on_import_config_clicked)
        file_menu.append(import_config_item)

        edit_menu = Gtk.Menu()
        edit_item = Gtk.MenuItem(label="Edit")
        edit_item.set_submenu(edit_menu)

        copy_item = Gtk.MenuItem(label="Copy")
        copy_item.connect("activate", self.on_copy_clicked)
        edit_menu.append(copy_item)

        cut_item = Gtk.MenuItem(label="Cut")
        cut_item.connect("activate", self.on_cut_clicked)
        edit_menu.append(cut_item)

        paste_item = Gtk.MenuItem(label="Paste")
        paste_item.connect("activate", self.on_paste_clicked)
        edit_menu.append(paste_item)

        delete_item = Gtk.MenuItem(label="Delete")
        delete_item.connect("activate", self.on_delete_clicked)
        edit_menu.append(delete_item)

        select_all_item = Gtk.MenuItem(label="Select All")
        select_all_item.connect("activate", self.on_select_all_clicked)
        edit_menu.append(select_all_item)

        undo_item = Gtk.MenuItem(label="Undo")
        undo_item.connect("activate", self.on_undo_clicked)
        edit_menu.append(undo_item)

        refresh_item = Gtk.MenuItem(label="Refresh Folder")
        refresh_item.connect("activate", self.on_refresh_clicked)
        edit_menu.append(refresh_item)

        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)

        show_directories_item = Gtk.CheckMenuItem(label="Show Directories")
        show_directories_item.set_active(self.file_manager.show_directories)
        show_directories_item.connect("toggled", self.on_show_directories_toggled)
        view_menu.append(show_directories_item)

        show_hidden_files_item = Gtk.CheckMenuItem(label="Show Hidden Files")
        show_hidden_files_item.set_active(self.file_manager.show_hidden_files)
        show_hidden_files_item.connect("toggled", self.on_show_hidden_files_toggled)
        view_menu.append(show_hidden_files_item)

        filter_by_type_item = Gtk.MenuItem(label="Filter by Type")
        filter_by_type_item.connect("activate", self.on_filter_by_type_clicked)
        view_menu.append(filter_by_type_item)

        self.menubar.append(file_item)
        self.menubar.append(edit_item)
        self.menubar.append(view_item)

        # Add keyboard shortcuts
        accel_group = Gtk.AccelGroup()
        self.add_accel_group(accel_group)
        show_directories_item.add_accelerator("activate", accel_group, Gdk.KEY_d, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        show_hidden_files_item.add_accelerator("activate", accel_group, Gdk.KEY_h, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        copy_item.add_accelerator("activate", accel_group, Gdk.KEY_c, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        cut_item.add_accelerator("activate", accel_group, Gdk.KEY_x, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        paste_item.add_accelerator("activate", accel_group, Gdk.KEY_v, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        delete_item.add_accelerator("activate", accel_group, Gdk.KEY_Delete, 0, Gtk.AccelFlags.VISIBLE)
        delete_item.add_accelerator("activate", accel_group, Gdk.KEY_BackSpace, 0, Gtk.AccelFlags.VISIBLE)
        refresh_item.add_accelerator("activate", accel_group, Gdk.KEY_r, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        undo_item.add_accelerator("activate", accel_group, Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)
        select_all_item.add_accelerator("activate", accel_group, Gdk.KEY_a, Gdk.ModifierType.CONTROL_MASK, Gtk.AccelFlags.VISIBLE)

    def create_folder_path_box(self, vbox):
        folder_box = Gtk.HBox(spacing=6)
        up_button = Gtk.Button(label="..")
        up_button.connect("clicked", self.on_up_clicked)
        folder_box.pack_start(up_button, False, False, 0)

        self.folder_path_entry = Gtk.Entry()
        self.folder_path_entry.set_editable(True)
        self.folder_path_entry.set_hexpand(True)
        self.folder_path_entry.connect("activate", self.on_folder_path_changed)
        folder_box.pack_start(self.folder_path_entry, True, True, 0)

        open_folder_button = Gtk.Button(label="Open")
        open_folder_button.connect("clicked", self.on_folder_clicked)
        folder_box.pack_start(open_folder_button, False, False, 0)

        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        folder_box.pack_start(refresh_button, False, False, 0)

        vbox.pack_start(folder_box, False, False, 0)

    def create_input_grid(self, vbox):
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(6)
        vbox.pack_start(grid, False, False, 0)

        self.prefix_entry = self.create_grid_entry(grid, "Prefix", 0, 0)
        self.suffix_entry = self.create_grid_entry(grid, "Suffix", 2, 0)
        self.remove_start_entry = self.create_grid_entry(grid, "Remove from Start", 0, 1)
        self.remove_end_entry = self.create_grid_entry(grid, "Remove from End", 2, 1)
        self.extension_entry = self.create_grid_entry(grid, "Add Extension", 0, 2)
        self.regex_find_entry = self.create_grid_entry(grid, "Regex Find", 0, 3)
        self.regex_replace_entry = self.create_grid_entry(grid, "Regex Replace", 2, 3)
        self.date_format_entry = self.create_grid_entry(grid, "Date Format", 0, 4)

        button_box = Gtk.HBox(spacing=6)
        self.preview_button = Gtk.Button(label="Preview Changes")
        self.preview_button.connect("clicked", self.on_preview_clicked)
        button_box.pack_start(self.preview_button, True, True, 0)

        self.rename_button = Gtk.Button(label="Rename Files")
        self.rename_button.connect("clicked", self.on_rename_clicked)
        button_box.pack_start(self.rename_button, True, True, 0)

        vbox.pack_start(button_box, False, False, 0)

    def create_grid_entry(self, grid, label, col, row):
        entry = Gtk.Entry()
        entry.set_placeholder_text(label)
        grid.attach(Gtk.Label(label=label), col, row, 1, 1)
        grid.attach(entry, col + 1, row, 1, 1)
        return entry

    def create_tree_view(self):
        self.liststore = Gtk.ListStore(bool, GdkPixbuf.Pixbuf, str, str, str, Gdk.RGBA)

        treeview = self.treeview
        treeview.set_model(self.liststore)
        treeview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        treeview.connect("row-activated", self.on_row_activated)

        renderer_toggle = Gtk.CellRendererToggle()
        renderer_toggle.connect("toggled", self.on_cell_toggled)
        column_toggle = Gtk.TreeViewColumn("Select", renderer_toggle, active=0)
        column_toggle.set_resizable(True)
        treeview.append_column(column_toggle)

        renderer_pixbuf = Gtk.CellRendererPixbuf()
        renderer_text = Gtk.CellRendererText()
        renderer_text.set_property("editable", True)
        renderer_text.connect("edited", self.on_cell_edited)
        column_filename = Gtk.TreeViewColumn("Filename")
        column_filename.pack_start(renderer_pixbuf, False)
        column_filename.pack_start(renderer_text, True)
        column_filename.add_attribute(renderer_pixbuf, "pixbuf", 1)
        column_filename.add_attribute(renderer_text, "text", 2)
        column_filename.add_attribute(renderer_text, "cell-background-rgba", 5)
        column_filename.set_resizable(True)
        treeview.append_column(column_filename)

        renderer_text = Gtk.CellRendererText()
        column_renamed = Gtk.TreeViewColumn("Renamed Filename", renderer_text, text=3)
        column_renamed.set_resizable(True)
        treeview.append_column(column_renamed)

        renderer_text = Gtk.CellRendererText()
        column_type = Gtk.TreeViewColumn("Type", renderer_text, text=4)
        column_type.set_resizable(True)
        treeview.append_column(column_type)

        treeview.connect("button-press-event", self.on_treeview_button_press)
        self.create_context_menu()

    def create_context_menu(self):
        self.context_menu = Gtk.Menu()

        copy_item = Gtk.MenuItem(label="Copy")
        copy_item.connect("activate", self.on_copy_clicked)
        self.context_menu.append(copy_item)

        cut_item = Gtk.MenuItem(label="Cut")
        cut_item.connect("activate", self.on_cut_clicked)
        self.context_menu.append(cut_item)

        paste_item = Gtk.MenuItem(label="Paste")
        paste_item.connect("activate", self.on_paste_clicked)
        self.context_menu.append(paste_item)

        delete_item = Gtk.MenuItem(label="Delete")
        delete_item.connect("activate", self.on_delete_clicked)
        self.context_menu.append(delete_item)

        select_item = Gtk.MenuItem(label="Select")
        select_item.connect("activate", self.on_select_clicked)
        self.context_menu.append(select_item)

        rename_item = Gtk.MenuItem(label="Rename")
        rename_item.connect("activate", self.on_rename_clicked)
        self.context_menu.append(rename_item)

        self.context_menu.show_all()

    def on_treeview_button_press(self, treeview, event):
        if event.button == 3:  # Right-click
            selection = treeview.get_selection()
            model, pathlist = selection.get_selected_rows()
            if pathlist:
                self.context_menu.popup(None, None, None, None, event.button, event.time)
                return True
        return False

    def on_treeview_key_press(self, treeview, event):
        focused_widget = Gtk.Window.get_focus(self)
        if isinstance(focused_widget, Gtk.Entry):
            return False  # Ignore if an entry widget is focused

        if event.keyval == Gdk.KEY_Return:  # Enter key
            self.select_files()
            return True
        elif event.keyval == Gdk.KEY_Delete or event.keyval == Gdk.KEY_BackSpace:  # Delete or Backspace key
            self.on_delete_clicked(None)
            return True
        elif event.keyval == Gdk.KEY_c and event.state & Gdk.ModifierType.CONTROL_MASK:  # Ctrl+C
            self.on_copy_clicked(None)
            return True
        elif event.keyval == Gdk.KEY_x and event.state & Gdk.ModifierType.CONTROL_MASK:  # Ctrl+X
            self.on_cut_clicked(None)
            return True
        elif event.keyval == Gdk.KEY_v and event.state & Gdk.ModifierType.CONTROL_MASK:  # Ctrl+V
            self.on_paste_clicked(None)
            return True
        elif event.keyval == Gdk.KEY_a and event.state & Gdk.ModifierType.CONTROL_MASK:  # Ctrl+A
            self.on_select_all_clicked(None)
            return True
        return False

    def on_cell_toggled(self, widget, path):
        self.liststore[path][0] = not self.liststore[path][0]

    def on_cell_edited(self, widget, path, new_text):
        self.liststore[path][2] = new_text

    def on_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        item_name = model[path][2]
        item_path = os.path.join(self.file_manager.folder_path, item_name)
        if os.path.isdir(item_path):
            self.file_manager.navigate_to(item_path)
            self.folder_path_entry.set_text(self.file_manager.folder_path)
            self.file_manager.load_files(self.liststore)

    def on_folder_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Please choose a folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.file_manager.navigate_to(dialog.get_filename())
            self.folder_path_entry.set_text(self.file_manager.folder_path)
            self.file_manager.load_files(self.liststore)
            logging.info("Folder selected: " + self.file_manager.folder_path)

        dialog.destroy()

    def on_folder_path_changed(self, widget):
        new_path = self.folder_path_entry.get_text()
        if self.file_manager.update_path(new_path):
            self.folder_path_entry.set_text(self.file_manager.folder_path)
            self.file_manager.load_files(self.liststore)
            logging.info("Folder path changed to: " + self.file_manager.folder_path)
        else:
            logging.warning("Invalid folder path")

    def on_up_clicked(self, widget):
        self.file_manager.navigate_up()
        self.folder_path_entry.set_text(self.file_manager.folder_path)
        self.file_manager.load_files(self.liststore)

    def on_refresh_clicked(self, widget):
        self.file_manager.load_files(self.liststore)

    def on_show_directories_toggled(self, widget):
        self.file_manager.show_directories = widget.get_active()
        self.file_manager.load_files(self.liststore)

    def on_show_hidden_files_toggled(self, widget):
        self.file_manager.show_hidden_files = widget.get_active()
        self.file_manager.load_files(self.liststore)

    def on_filter_by_type_clicked(self, widget):
        dialog = Gtk.Dialog(title="Filter by Type", parent=self, modal=True)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Enter file type (e.g., TXT, PNG, ...)")
        entry_box = dialog.get_content_area()
        entry_box.pack_start(entry, True, True, 0)
        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_type = entry.get_text().upper()
            self.file_manager.set_file_type_filter(file_type)
            self.file_manager.load_files(self.liststore)
        dialog.destroy()

    def on_preview_clicked(self, widget):
        prefix = self.prefix_entry.get_text()
        suffix = self.suffix_entry.get_text()
        try:
            remove_start = int(self.remove_start_entry.get_text())
        except ValueError:
            remove_start = 0
        try:
            remove_end = int(self.remove_end_entry.get_text())
        except ValueError:
            remove_end = 0
        extension = self.extension_entry.get_text()
        regex_find = self.regex_find_entry.get_text()
        regex_replace = self.regex_replace_entry.get_text()
        date_format = self.date_format_entry.get_text()

        for row in self.liststore:
            if row[0]:  # If selected
                original_name = row[2]
                name, ext = os.path.splitext(original_name)

                if remove_start > 0:
                    name = name[remove_start:]
                if remove_end > 0:
                    name = name[:-remove_end]

                if regex_find:
                    name = re.sub(regex_find, regex_replace, name)

                if date_format:
                    name = self.recognize_date(name, date_format)

                new_name = f"{prefix}{name}{suffix}{ext}"

                if extension:
                    new_name = f"{prefix}{name}{suffix}{extension}"

                row[3] = new_name

    def on_rename_clicked(self, widget):
        for row in self.liststore:
            if row[0]:  # If selected
                original_name = row[2]
                new_name = row[3]
                original_path = next((f for f in self.file_manager.file_list if os.path.basename(f) == original_name), None)
                if original_path:
                    directory = os.path.dirname(original_path)
                    new_path = os.path.join(directory, new_name)
                    os.rename(original_path, new_path)
                    self.undo_stack.append(('rename', original_path, new_path))  # Record rename operation
                    logging.info(f"Renamed {original_path} to {new_path}")

        logging.info("Renaming completed")
        self.file_manager.load_files(self.liststore)  # Refresh the folder

    def recognize_date(self, text, date_format):
        date_patterns = [
            r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b',  # yyyy-mm-dd, yyyy/mm/dd
            r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b',  # mm-dd-yyyy, mm/dd/yyyy
            r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b',  # d-m-yy, dd-mm-yyyy, etc.
            r'\b(\d{8})\b'  # yyyymmdd
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    date = dateparser.parse(match.group(0))
                    return text.replace(match.group(0), date.strftime(date_format))
                except ValueError:
                    continue
        return text

    def on_copy_clicked(self, widget):
        self.copied_files = self.get_selected_files()
        self.cut_files = []  # Clear cut files
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text("\n".join(self.copied_files), -1)
        logging.info(f"Copied files: {self.copied_files}")

    def on_cut_clicked(self, widget):
        self.cut_files = self.get_selected_files()
        self.copied_files = []  # Clear copied files
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text("\n".join(self.cut_files), -1)
        logging.info(f"Cut files: {self.cut_files}")
        self.update_cut_file_visuals()

    def update_cut_file_visuals(self):
        for row in self.liststore:
            if os.path.join(self.file_manager.folder_path, row[2]) in self.cut_files:
                row[5] = Gdk.RGBA(0.5, 0.5, 0.5, 0.5)  # Darker color for cut files
            else:
                row[5] = Gdk.RGBA(1, 1, 1, 1)  # Normal color for other files

    def on_paste_clicked(self, widget):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.request_text(self.on_paste_clipboard_received)

    def on_paste_clipboard_received(self, clipboard, text):
        if text:
            paths = text.split("\n")
            for file_path in paths:
                if os.path.exists(file_path):
                    if self.cut_files:
                        new_path = os.path.join(self.file_manager.folder_path, os.path.basename(file_path))
                        shutil.move(file_path, new_path)
                        self.undo_stack.append(('move', file_path, new_path))  # Record move operation
                        logging.info(f"Moved {file_path} to {self.file_manager.folder_path}")
                    else:
                        new_path = os.path.join(self.file_manager.folder_path, os.path.basename(file_path))
                        shutil.copy(file_path, new_path)
                        self.undo_stack.append(('copy', file_path, new_path))  # Record copy operation
                        logging.info(f"Pasted {file_path} to {self.file_manager.folder_path}")
            self.cut_files = []  # Clear cut files after moving
            self.file_manager.load_files(self.liststore)
        else:
            Notify.Notification.new("Paste Error", "No valid file path in clipboard", None).show()

    def on_delete_clicked(self, widget):
        for row in self.liststore:
            if row[0]:  # If selected
                file_path = os.path.join(self.file_manager.folder_path, row[2])
                send2trash(file_path)  # Move the file to trash using send2trash
                self.undo_stack.append(('delete', file_path, None))  # Record delete operation
                logging.info(f"Moved to trash: {file_path}")
        self.file_manager.load_files(self.liststore)

    def on_select_clicked(self, widget):
        self.select_files()

    def select_files(self):
        selection = self.treeview.get_selection()
        model, paths = selection.get_selected_rows()
        for path in paths:
            self.liststore[path][0] = True

    def on_select_all_clicked(self, widget):
        selection = self.treeview.get_selection()
        selection.select_all()
        model, paths = selection.get_selected_rows()
        for path in paths:
            self.liststore[path][0] = True

    def on_undo_clicked(self, widget):
        if self.undo_stack:
            operation, src, dest = self.undo_stack.pop()
            if operation == 'rename':
                os.rename(dest, src)
                logging.info(f"Undo rename: {dest} to {src}")
            elif operation == 'move':
                shutil.move(dest, src)
                logging.info(f"Undo move: {dest} to {src}")
            elif operation == 'copy':
                os.remove(dest)
                logging.info(f"Undo copy: Removed {dest}")
            elif operation == 'delete':
                # Restoring deleted files from trash is not straightforward and might not be cross-platform compatible
                logging.warning(f"Undo delete not supported: {src}")

            self.file_manager.load_files(self.liststore)

    def on_save_config_clicked(self, widget):
        config = {
            "prefix": self.prefix_entry.get_text(),
            "suffix": self.suffix_entry.get_text(),
            "remove_start": self.remove_start_entry.get_text(),
            "remove_end": self.remove_end_entry.get_text(),
            "extension": self.extension_entry.get_text(),
            "regex_find": self.regex_find_entry.get_text(),
            "regex_replace": self.regex_replace_entry.get_text(),
            "date_format": self.date_format_entry.get_text()
        }
        dialog = Gtk.FileChooserDialog(
            title="Save Configuration", parent=self, action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            with open(dialog.get_filename(), 'w') as f:
                json.dump(config, f)
            logging.info(f"Configuration saved to {dialog.get_filename()}")
        dialog.destroy()

    def on_import_config_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Import Configuration", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.load_config(dialog.get_filename())
        dialog.destroy()

    def load_config(self, config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            self.prefix_entry.set_text(config.get("prefix", ""))
            self.suffix_entry.set_text(config.get("suffix", ""))
            self.remove_start_entry.set_text(config.get("remove_start", ""))
            self.remove_end_entry.set_text(config.get("remove_end", ""))
            self.extension_entry.set_text(config.get("extension", ""))
            self.regex_find_entry.set_text(config.get("regex_find", ""))
            self.regex_replace_entry.set_text(config.get("regex_replace", ""))
            self.date_format_entry.set_text(config.get("date_format", ""))
        logging.info(f"Configuration imported from {config_path}")

    def get_selected_files(self):
        selection = self.treeview.get_selection()
        model, paths = selection.get_selected_rows()
        return [os.path.join(self.file_manager.folder_path, model[path][2]) for path in paths]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Renamr")
    parser.add_argument("directory", nargs='?', default=os.path.expanduser("~"), help="Directory to open")
    parser.add_argument("--config", help="Configuration file to load", default=None)
    parser.add_argument("-v", "--verbose", help="Verbose level (debug, info, warning, error, critical)", default="info")

    args = parser.parse_args()
    folder_path = os.path.abspath(os.path.expanduser(args.directory))
    config_path = os.path.abspath(os.path.expanduser(args.config)) if args.config else None
    verbose_level = getattr(logging, args.verbose.upper(), logging.INFO)

    win = Renamr(folder_path=folder_path, config_path=config_path, verbose_level=verbose_level)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
