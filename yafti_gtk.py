#!/usr/bin/env python3
"""
Yafti GTK - A simple GTK GUI for running scripts from yafti.yml
"""

import gi
import yaml
import subprocess
import os
import sys

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Vte, GLib, Gio
import configparser


def _read_ini_value(path, section, key):
    parser = configparser.ConfigParser()
    parser.optionxform = str
    try:
        if os.path.exists(path):
            parser.read(path)
            return parser.get(section, key, fallback=None)
    except Exception:
        pass
    return None


def _detect_dark_preference():
    """Detect if system prefers dark theme without initializing GTK."""
    prefers_dark = True  # default to dark

    # Check portal for color-scheme preference
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            bus, Gio.DBusProxyFlags.NONE, None,
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop',
            'org.freedesktop.portal.Settings',
            None,
        )
        variant = proxy.call_sync(
            'Read',
            GLib.Variant('(ss)', ('org.freedesktop.appearance', 'color-scheme')),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        read_value = variant.get_child_value(0)
        color_scheme = read_value.unpack() if hasattr(read_value, 'unpack') else read_value
        # Portal values: 0 = default, 1 = prefer-dark, 2 = prefer-light
        if color_scheme == 1:
            prefers_dark = True
        elif color_scheme == 2:
            prefers_dark = False
    except Exception:
        pass

    # Fallback: GSettings
    if not prefers_dark:
        try:
            interface = Gio.Settings.new('org.gnome.desktop.interface')
            color_scheme = interface.get_string('color-scheme') if interface else ''
            if color_scheme == 'prefer-dark':
                prefers_dark = True
            elif not prefers_dark:
                theme_name = interface.get_string('gtk-theme') if interface else ''
                prefers_dark = 'dark' in theme_name.lower()
        except Exception:
            pass

    # Fallback: GTK_THEME env
    if not prefers_dark:
        gtk_theme_env = os.environ.get('GTK_THEME', '')
        if 'dark' in gtk_theme_env.lower():
            prefers_dark = True

    # Fallback: gtk settings.ini
    if not prefers_dark:
        ini_val = _read_ini_value(os.path.expanduser('~/.config/gtk-3.0/settings.ini'), 'Settings', 'gtk-application-prefer-dark-theme')
        if ini_val and ini_val.strip() == '1':
            prefers_dark = True
        if not prefers_dark:
            ini_theme = _read_ini_value(os.path.expanduser('~/.config/gtk-3.0/settings.ini'), 'Settings', 'gtk-theme-name')
            if ini_theme and 'dark' in ini_theme.lower():
                prefers_dark = True

    # Fallback: KDE
    if not prefers_dark:
        kde_scheme = _read_ini_value(os.path.expanduser('~/.config/kdeglobals'), 'General', 'ColorScheme')
        if kde_scheme and 'dark' in kde_scheme.lower():
            prefers_dark = True

    return prefers_dark


def setup_theme():
    """Detect and apply system theme preference at startup."""
    prefers_dark = _detect_dark_preference()
    
    # Ensure app-id matches desktop file so icon/theme resolve correctly on Wayland
    GLib.set_prgname('com.github.yafti.gtk')

    # Set GTK_THEME env before GTK init
    if prefers_dark:
        os.environ['GTK_THEME'] = 'Adwaita:dark'
    else:
        os.environ.pop('GTK_THEME', None)
    
    # Initialize GTK
    Gtk.init([])

    # Advertise app icon for headerbar/titlebar; fall back to on-disk SVG if lookup fails
    try:
        Gtk.Window.set_default_icon_name('com.github.yafti.gtk')
    except Exception:
        pass
    icon_path = '/app/share/icons/hicolor/scalable/apps/com.github.yafti.gtk.svg'
    if os.path.exists(icon_path):
        try:
            Gtk.Window.set_default_icon_from_file(icon_path)
        except Exception:
            pass
    
    # Set GTK theme properties
    settings = Gtk.Settings.get_default()
    if settings:
        settings.set_property('gtk-application-prefer-dark-theme', prefers_dark)


class YaftiGTK(Gtk.Window):
    def __init__(self, config_file='yafti.yml'):
        super().__init__(title="Bazzite Portal")
        self.set_default_size(800, 600)
        self.set_border_width(10)
        
        # Load YAML configuration
        self.config = self.load_config(config_file)
        self.screens = self.config.get('screens', [])
        self.actions_index = self._build_actions_index()
        
        # Create main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)
        
        # Navigation bar (back button + current category label)
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.back_button = Gtk.Button(label="Back")
        self.back_button.connect("clicked", self.show_home)
        self.back_button.set_no_show_all(True)
        self.back_button.hide()
        nav_box.pack_start(self.back_button, False, False, 0)
        self.section_label = Gtk.Label()
        self.section_label.set_xalign(0)
        nav_box.pack_start(self.section_label, True, True, 0)
        nav_box.set_no_show_all(True)
        nav_box.hide()
        self.nav_box = nav_box
        vbox.pack_start(nav_box, False, False, 0)

        # Stack to swap between home (categories) and screens
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)

        home_page = self.create_categories_page()
        self.stack.add_named(home_page, "home")

        self.screen_pages = []
        for idx, screen in enumerate(self.screens):
            page = self.create_screen_page(screen)
            screen_name = f"screen-{idx}"
            self.screen_pages.append((screen_name, screen))
            self.stack.add_named(page, screen_name)

        vbox.pack_start(self.stack, True, True, 0)

        # Start at home view
        self.show_home()
        # Status bar removed to avoid confusing "Running" messages during scripts
        self.statusbar = None
        self.status_context = None
        
    def load_config(self, config_file):
        """Load and parse the YAML configuration file"""
        try:
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Configuration file not found"
            )
            dialog.format_secondary_text(
                f"Could not find {config_file} in the current directory."
            )
            dialog.run()
            dialog.destroy()
            sys.exit(1)
        except yaml.YAMLError as e:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="YAML parsing error"
            )
            dialog.format_secondary_text(str(e))
            dialog.run()
            dialog.destroy()
            sys.exit(1)
    
    def create_screen_page(self, screen):
        """Create a page for a screen with all its actions"""
        # Create scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        # Create main box for the page
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page_box.set_margin_top(10)
        page_box.set_margin_bottom(10)
        page_box.set_margin_start(10)
        page_box.set_margin_end(10)
        
        # Add description
        if screen.get('description'):
            desc_label = Gtk.Label(label=screen['description'])
            desc_label.set_line_wrap(True)
            desc_label.set_xalign(0)
            desc_label.set_margin_bottom(10)
            page_box.pack_start(desc_label, False, False, 0)
            
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            page_box.pack_start(separator, False, False, 0)
        
        # Create action items
        for action in screen.get('actions', []):
            action_box = self.create_action_item(action)
            page_box.pack_start(action_box, False, False, 0)
        
        scrolled.add(page_box)
        return scrolled
    
    def create_action_item(self, action):
        """Create a clickable action item"""
        # Create a button for the action
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        
        # Create box for button content
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_margin_top(5)
        button_box.set_margin_bottom(5)
        button_box.set_margin_start(5)
        button_box.set_margin_end(5)
        
        # Add icon (play button)
        icon = Gtk.Image.new_from_icon_name("media-playback-start", Gtk.IconSize.BUTTON)
        button_box.pack_start(icon, False, False, 0)
        
        # Create text box
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        
        # Title label
        title_label = Gtk.Label()
        title_label.set_markup(f"<b>{action.get('title', 'Action')}</b>")
        title_label.set_xalign(0)
        text_box.pack_start(title_label, False, False, 0)
        
        # Description label
        if action.get('description'):
            desc_label = Gtk.Label(label=action['description'])
            desc_label.set_xalign(0)
            desc_label.set_line_wrap(True)
            desc_label.set_max_width_chars(60)
            desc_label.get_style_context().add_class('dim-label')
            text_box.pack_start(desc_label, False, False, 0)
        
        button_box.pack_start(text_box, True, True, 0)
        button.add(button_box)
        
        # Connect click event
        script = action.get('script', '')
        button.connect("clicked", self.on_action_clicked, action.get('title', 'Action'), script)
        
        # Add frame around button
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.add(button)
        
        return frame

    def _build_actions_index(self):
        """Flatten actions for search lookup."""
        index = []
        for screen in self.screens or []:
            for action in screen.get('actions', []):
                index.append({'screen_title': screen.get('title', ''), 'action': action})
        # Add rebase helper as a top-level action for search
        index.append({
            'screen_title': 'Rebase',
            'action': {
                'title': 'Rebase Bazzite',
                'description': 'Rebase your Bazzite install to another version or image',
                'script': 'brh'
            }
        })
        # Add update helper as a top-level action for search
        index.append({
            'screen_title': 'Update',
            'action': {
                'title': 'Update Bazzite and Apps',
                'description': 'Updates Bazzite, Flatpaks, firmware, and more',
                'script': 'ujust update'
            }
        })
        return index

    def create_categories_page(self):
        """Home page listing categories (screens)."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_top(8)
        outer.set_margin_bottom(12)
        outer.set_margin_start(14)
        outer.set_margin_end(14)

        # Search field (kept outside scrolled content so it stays fixed)
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Search Apps and Actions")
        search_entry.set_width_chars(32)
        search_entry.set_halign(Gtk.Align.CENTER)
        search_entry.set_margin_bottom(6)
        search_entry.connect("search-changed", self.on_search_changed)
        search_entry.connect("changed", self.on_search_changed)
        self.search_entry = search_entry
        outer.pack_start(search_entry, False, False, 0)

        # Scrolled area for results + categories
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # Search results area (hidden when empty)
        self.search_results_revealer = Gtk.Revealer()
        self.search_results_revealer.set_reveal_child(False)
        self.search_results_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.search_results_box = results_box
        self.search_results_revealer.add(results_box)
        content.pack_start(self.search_results_revealer, False, False, 0)

        # Center a vertical stack of category buttons (+ rebase helper)
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_valign(Gtk.Align.CENTER)
        container.set_halign(Gtk.Align.CENTER)
        self.categories_container = container

        # Update helper at the top
        update_card = self.create_update_button()
        update_card.set_margin_top(8)
        container.pack_start(update_card, False, False, 0)

        # Category cards
        for idx, screen in enumerate(self.screens):
            screen_name = f"screen-{idx}"
            card = self.create_category_button(screen, screen_name)
            container.pack_start(card, False, False, 0)

        # Rebase helper at the bottom
        rebase_card = self.create_rebase_button()
        rebase_card.set_margin_top(8)
        container.pack_start(rebase_card, False, False, 0)

        content.pack_start(container, True, True, 0)
        scrolled.add(content)

        outer.pack_start(scrolled, True, True, 0)
        return outer

    def create_category_button(self, screen, screen_name):
        """Create a clickable card for a category (screen)."""
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_margin_top(10)
        outer.set_margin_bottom(10)
        outer.set_margin_start(10)
        outer.set_margin_end(10)

        title = Gtk.Label()
        title.set_markup(f"<b>{screen.get('title', 'Category')}</b>")
        title.set_xalign(0)
        outer.pack_start(title, False, False, 0)

        if screen.get('description'):
            desc = Gtk.Label(label=screen['description'])
            desc.set_xalign(0)
            desc.set_line_wrap(True)
            desc.set_max_width_chars(60)
            desc.get_style_context().add_class('dim-label')
            outer.pack_start(desc, False, False, 0)

        button.add(outer)
        button.connect("clicked", self.show_screen, screen_name, screen.get('title', ''))
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.add(button)
        return frame

    def create_action_result(self, action, screen_title):
        """Render a search result as a labeled action card."""
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        wrapper.pack_start(self.create_action_item(action), False, False, 0)
        return wrapper

    def create_rebase_button(self):
        """Direct action button to run BRH helper without a category page."""
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title = Gtk.Label()
        title.set_markup("<b>Rebase Bazzite</b>")
        title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        desc = Gtk.Label(label="Rebase your Bazzite install to another version or image")
        desc.set_xalign(0)
        desc.set_line_wrap(True)
        desc.set_max_width_chars(60)
        desc.get_style_context().add_class('dim-label')
        box.pack_start(desc, False, False, 0)

        button.add(box)
        button.connect("clicked", self.on_action_clicked, "Rebase Bazzite", "brh")

        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.add(button)
        return frame

    def create_update_button(self):
        """Direct action button to run ujust update on the host."""
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title = Gtk.Label()
        title.set_markup("<b>Update Bazzite and Apps</b>")
        title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        desc = Gtk.Label(label="Updates Bazzite, Flatpaks, firmware, and more")
        desc.set_xalign(0)
        desc.set_line_wrap(True)
        desc.set_max_width_chars(60)
        desc.get_style_context().add_class('dim-label')
        box.pack_start(desc, False, False, 0)

        button.add(box)
        button.connect("clicked", self.on_action_clicked, "Update Bazzite and Apps", "ujust update")

        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.add(button)
        return frame

    def _clear_search_results(self):
        for child in self.search_results_box.get_children():
            self.search_results_box.remove(child)
        self.search_results_revealer.set_reveal_child(False)
        if hasattr(self, 'categories_container'):
            self.categories_container.show()

    def on_search_changed(self, entry):
        query = entry.get_text().strip()
        if not query:
            self._clear_search_results()
            if hasattr(self, 'categories_container'):
                self.categories_container.show()
            return

        lowered = query.lower()
        matches = []
        for item in self.actions_index:
            action = item['action']
            title = action.get('title', '')
            desc = action.get('description', '')
            if lowered in title.lower() or lowered in desc.lower():
                matches.append(item)

        self._clear_search_results()
        header = Gtk.Label()
        header.set_markup("<b>Search results</b>")
        header.set_xalign(0)
        self.search_results_box.pack_start(header, False, False, 0)

        if matches:
            for item in matches:
                result = self.create_action_result(item['action'], item['screen_title'])
                self.search_results_box.pack_start(result, False, False, 0)
        else:
            empty = Gtk.Label(label="No matches found")
            empty.set_xalign(0)
            self.search_results_box.pack_start(empty, False, False, 0)

        self.search_results_box.show_all()
        self.search_results_revealer.set_reveal_child(True)
        if hasattr(self, 'categories_container'):
            self.categories_container.hide()

    def show_home(self, *args):
        """Navigate back to category list."""
        self.stack.set_visible_child_name("home")
        self.back_button.hide()
        self.nav_box.hide()
        self.section_label.set_text("")
        if hasattr(self, 'search_entry'):
            self.search_entry.set_text("")
        if hasattr(self, '_clear_search_results'):
            self._clear_search_results()

    def show_screen(self, button, screen_name, screen_title):
        """Show a specific screen/page of actions."""
        self.stack.set_visible_child_name(screen_name)
        self.back_button.show()
        self.nav_box.show()
        self.section_label.set_text(screen_title or "")
        if hasattr(self, 'search_entry'):
            self.search_entry.set_text("")
        if hasattr(self, '_clear_search_results'):
            self._clear_search_results()
    
    def on_action_clicked(self, button, title, script):
        """Handle action button click - run script in terminal window"""
        if not script:
            if self.statusbar:
                self.statusbar.push(self.status_context, "No script defined for this action")
            return

        # Prefer host terminal for BRH and ujust commands
        if script:
            trimmed = script.strip()
            if trimmed == 'brh' or trimmed.startswith('ujust '):
                if self.launch_host_terminal(trimmed):
                    return
        
        # Update statusbar
        if self.statusbar:
            self.statusbar.push(self.status_context, f"Running: {title}")
        
        # Create dialog with terminal
        dialog = Gtk.Dialog(
            title=f"Running: {title}",
            transient_for=self,
            flags=0
        )
        dialog.set_default_size(700, 400)
        
        # Create terminal widget
        terminal = Vte.Terminal()
        terminal.set_scroll_on_output(True)
        terminal.set_scrollback_lines(10000)
        
        # Create scrolled window for terminal
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(terminal)
        
        dialog.vbox.pack_start(scrolled, True, True, 0)
        
        # Add close button
        close_button = dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        
        # Show dialog
        dialog.show_all()
        
        # Spawn the script in the terminal. When running inside a Flatpak sandbox
        # prefer `flatpak-spawn --host` so `ujust` and other host tools run on the host.
        try:
            if os.environ.get('FLATPAK_ID'):
                cmd = ['/usr/bin/flatpak-spawn', '--host', '/bin/bash', '-c', script]
            else:
                cmd = ['/bin/bash', '-c', script]

            terminal.spawn_async(
                Vte.PtyFlags.DEFAULT,
                os.getcwd(),
                cmd,
                None,
                GLib.SpawnFlags.DEFAULT,
                None,
                None,
                -1,
                None,
                self.on_terminal_spawn_callback,
                (dialog, title)
            )
        except Exception as e:
            error_dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Error running script"
            )
            error_dialog.format_secondary_text(str(e))
            error_dialog.run()
            error_dialog.destroy()
            dialog.destroy()
        
        # Handle dialog response
        dialog.connect("response", lambda d, r: d.destroy())

    def launch_host_terminal(self, script):
        """Attempt to run a command in host KDE Ptyxis. Returns True if launched."""
        try:
            # Use flatpak-spawn to open host ptyxis and run the command
            cmd = [
                '/usr/bin/flatpak-spawn', '--host', 'ptyxis',
                '--', 'bash', '--noprofile', '--norc', '-lc', script
            ]
            subprocess.Popen(cmd)
            return True
        except Exception as e:
            print(f"Host terminal launch failed: {e}")
            return False
    
    def on_terminal_spawn_callback(self, terminal, pid, error, user_data, *args):
        """Callback after terminal spawn"""
        dialog = None
        title = "Action"
        if isinstance(user_data, (tuple, list)) and len(user_data) == 2:
            dialog, title = user_data
        else:
            dialog = user_data if isinstance(user_data, Gtk.Dialog) else None

        if error:
            if self.statusbar:
                self.statusbar.push(self.status_context, f"Error running {title}")
            print(f"Error: {error}")
            return
        if dialog:
            terminal.connect("child-exited", self.on_terminal_child_exited, dialog, title)
    
    def on_terminal_child_exited(self, terminal, status, dialog, title):
        """Handle terminal process exit"""
        if self.statusbar:
            if status == 0:
                self.statusbar.push(self.status_context, f"Completed: {title}")
            else:
                self.statusbar.push(self.status_context, f"Failed: {title} (exit code: {status})")


def main():
    # Apply theme before creating window
    setup_theme()

    # Use host-provided Bazzite portal config
    config_file = '/run/host/usr/share/yafti/yafti.yml'
    if not os.path.exists(config_file):
        print(f"Error: yafti config not found at {config_file}")
        sys.exit(1)
    
    # Create and show window
    win = YaftiGTK(config_file)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()
