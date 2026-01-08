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
from gi.repository import Gtk, Vte, GLib


def setup_theme():
    """Apply dark theme at startup."""
    # Ensure app-id matches desktop file so icon/theme resolve correctly on Wayland
    GLib.set_prgname('com.github.yafti.gtk')

    # Set dark theme
    os.environ['GTK_THEME'] = 'Adwaita:dark'
    
    # Initialize GTK
    Gtk.init([])

    # Set app icon - icon theme should resolve this properly in flatpak
    try:
        Gtk.Window.set_default_icon_name('com.github.yafti.gtk')
    except Exception as e:
        print(f"Warning: Could not set app icon: {e}")
    
    # Enable dark theme preference
    settings = Gtk.Settings.get_default()
    if settings:
        settings.set_property('gtk-application-prefer-dark-theme', True)


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
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)
        
        # Search bar at the top
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Search Apps and Actions")
        search_entry.set_margin_top(4)
        search_entry.set_margin_bottom(4)
        search_entry.set_margin_start(4)
        search_entry.set_margin_end(4)
        search_entry.connect("search-changed", self.on_search_changed)
        search_entry.connect("changed", self.on_search_changed)
        self.search_entry = search_entry
        vbox.pack_start(search_entry, False, False, 0)

        # Notebook (tabs) directly below search
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        
        # Add tabs for each screen from YAML
        for screen in self.screens:
            page = self.create_screen_page(screen)
            label = Gtk.Label(label=screen.get('title', 'Tab'))
            self.notebook.append_page(page, label)

        # Stack to switch between notebook and search results
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.content_stack.set_transition_duration(150)
        
        # Add notebook to stack
        self.content_stack.add_named(self.notebook, "tabs")
        
        # Search results page
        search_scrolled = Gtk.ScrolledWindow()
        search_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        results_box.set_margin_top(10)
        results_box.set_margin_bottom(10)
        results_box.set_margin_start(10)
        results_box.set_margin_end(10)
        self.search_results_box = results_box
        search_scrolled.add(results_box)
        self.content_stack.add_named(search_scrolled, "search")
        
        # Start with tabs visible
        self.content_stack.set_visible_child_name("tabs")
        
        vbox.pack_start(self.content_stack, True, True, 0)
        
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
        return index

    def create_action_result(self, action, screen_title):
        """Render a search result as a labeled action card."""
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        wrapper.pack_start(self.create_action_item(action), False, False, 0)
        return wrapper

    def _clear_search_results(self):
        for child in self.search_results_box.get_children():
            self.search_results_box.remove(child)
        if hasattr(self, 'content_stack'):
            self.content_stack.set_visible_child_name("tabs")

    def on_search_changed(self, entry):
        query = entry.get_text().strip()
        if not query:
            self._clear_search_results()
            return

        lowered = query.lower()
        matches = []
        for item in self.actions_index:
            action = item['action']
            title = action.get('title', '')
            desc = action.get('description', '')
            if lowered in title.lower() or lowered in desc.lower():
                matches.append(item)

        # Clear old results
        for child in self.search_results_box.get_children():
            self.search_results_box.remove(child)
        
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
        if hasattr(self, 'content_stack'):
            self.content_stack.set_visible_child_name("search")
    
    def on_action_clicked(self, button, title, script):
        """Handle action button click - run script in terminal window"""
        if not script:
            return

        # Try host terminal first; fall back to embedded VTE if it fails
        if self.launch_host_terminal(script.strip()):
            return
        
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
        
        # Spawn the script in the terminal using flatpak-spawn to execute on the host
        # so ujust and other host tools are available
        try:
            cmd = ['/usr/bin/flatpak-spawn', '--host', '/bin/bash', '-c', script]

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
        """Attempt to run a command in a host terminal. Returns True if launched."""
        candidate_terminals = [
            "ptyxis",
            "konsole",
            "gnome-terminal",
            "xterm",
        ]
        
        for terminal in candidate_terminals:
            try:
                # First check if terminal exists on host
                check = subprocess.run(
                    ["/usr/bin/flatpak-spawn", "--host", "which", terminal],
                    capture_output=True,
                    timeout=2
                )
                if check.returncode != 0:
                    continue  # Terminal not found, try next
                    
                # Terminal exists, launch it
                cmd = [
                    "/usr/bin/flatpak-spawn",
                    "--host",
                    terminal,
                    "--",
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-lc",
                    script,
                ]
                subprocess.Popen(cmd)
                return True
            except Exception as e:
                print(f"Host terminal '{terminal}' launch failed: {e}")
                continue
        
        print("Host terminal launch failed: no suitable terminal found.")
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
            print(f"Error spawning terminal for {title}: {error}")
            return
        if dialog:
            terminal.connect("child-exited", self.on_terminal_child_exited, dialog, title)
    
    def on_terminal_child_exited(self, terminal, status, dialog, title):
        """Handle terminal process exit"""
        if status != 0:
            print(f"Script '{title}' exited with code {status}")


def main():
    import argparse
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        prog='com.github.yafti.gtk',
        description='Bazzite Portal - GTK interface for yafti',
        epilog='Example: flatpak run com.github.yafti.gtk /run/host/usr/share/yafti/yafti.yml'
    )
    parser.add_argument(
        'config',
        metavar='CONFIG_FILE',
        help='Path to yafti.yml configuration file'
    )
    args = parser.parse_args()
    
    # Apply theme before creating window
    setup_theme()

    # Use provided config file
    config_file = args.config
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
