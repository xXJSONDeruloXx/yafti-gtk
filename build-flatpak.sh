#!/bin/bash
set -e

echo "Building Yafti GTK Flatpak..."

# Check for flatpak-builder
if ! command -v flatpak-builder &> /dev/null; then
    echo "Error: flatpak-builder not found. Please install it first."
    echo "  Fedora: sudo dnf install flatpak-builder"
    echo "  Arch: sudo pacman -S flatpak-builder"
    echo "  Debian/Ubuntu: sudo apt-get install flatpak-builder"
    exit 1
fi

# Add Flathub repo if not present
if ! flatpak remote-list --user | grep -q flathub; then
    echo "Adding Flathub repository..."
    flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo
fi

# Install runtime and SDK
echo "Installing GNOME runtime and SDK..."
if ! flatpak install -y --user flathub org.gnome.Platform//48 org.gnome.Sdk//48; then
    echo "Warning: Failed to install runtimes. They may already be installed."
    echo "Continuing with build..."
fi

# Build the flatpak
echo "Building flatpak package..."
# Build without installing (installation happens outside container)
flatpak-builder --disable-rofiles-fuse --user --force-clean build-dir com.github.yafti.gtk.yml --repo=repo

# Export the flatpak bundle
echo "Exporting flatpak bundle..."
mkdir -p output
flatpak build-bundle repo output/yafti-gtk.flatpak com.github.yafti.gtk

echo ""
echo "✓ Build complete!"
echo "✓ Flatpak bundle exported: output/yafti-gtk.flatpak"
echo ""
echo "To test the app:"
echo "  flatpak run com.github.yafti.gtk"
echo ""
echo "To install the bundle on another system:"
echo "  flatpak install yafti-gtk.flatpak"
