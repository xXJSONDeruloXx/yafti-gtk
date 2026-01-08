#!/bin/bash
set -e

echo "Building Yafti GTK Flatpak..."

# Check for flatpak-builder from Flathub
if ! flatpak list --user | grep -q org.flatpak.Builder; then
    echo "Error: org.flatpak.Builder not found. Installing from Flathub..."
    flatpak install --user -y flathub org.flatpak.Builder || exit 1
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
flatpak run org.flatpak.Builder --disable-rofiles-fuse --user --force-clean build-dir com.github.yafti.gtk.yml --repo=repo

# Export the flatpak bundle
echo "Exporting flatpak bundle..."
flatpak build-bundle repo yafti-gtk.flatpak com.github.yafti.gtk

echo ""
echo "✓ Build complete!"
echo "✓ Flatpak bundle exported: yafti-gtk.flatpak"
echo ""
echo "To test the app:"
echo "  flatpak run com.github.yafti.gtk"
echo ""
echo "To install the bundle on another system:"
echo "  flatpak install yafti-gtk.flatpak"
