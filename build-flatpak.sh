#!/bin/bash
set -e

echo "Building Yafti GTK Flatpak..."

## Prerequisite checks
if ! command -v flatpak >/dev/null 2>&1; then
    echo "Error: 'flatpak' command not found. Please install Flatpak." >&2
    exit 1
fi

echo "Checking repository manifest..."
if [ ! -f com.github.yafti.gtk.yml ]; then
    echo "Error: manifest 'com.github.yafti.gtk.yml' not found in repository root." >&2
    exit 1
fi

echo "Ensuring Flathub remote is present (user)":
if ! flatpak remote-list --user | grep -q flathub; then
    echo "Flathub remote not found; attempting to add..."
    if ! flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo; then
        echo "Error: failed to add Flathub remote." >&2
        exit 1
    fi
fi

echo "Checking org.flatpak.Builder (user)..."
if ! flatpak --user list | grep -q org.flatpak.Builder; then
    echo "org.flatpak.Builder not found; installing..."
    if ! flatpak install --user -y flathub org.flatpak.Builder; then
        echo "Error: failed to install org.flatpak.Builder." >&2
        exit 1
    fi
fi

echo "Installing/ensuring GNOME runtime and SDK (user)..."
if ! flatpak --user list | grep -q 'org.gnome.Platform/x86_64/48' || ! flatpak --user list | grep -q 'org.gnome.Sdk/x86_64/48'; then
    if ! flatpak install -y --user flathub org.gnome.Platform//48 org.gnome.Sdk//48; then
        echo "Warning: attempted to install GNOME runtime/SDK but the install command failed." >&2
    fi
fi

# Verify the GNOME SDK is available for the user installation
echo "Verifying GNOME SDK 48 is installed..."
if ! flatpak --user list | grep -q 'org.gnome.Sdk/x86_64/48'; then
    echo "Error: org.gnome.Sdk version 48 not found after install. Aborting." >&2
    exit 1
fi

mkdir -p repo build-dir || { echo "Error: cannot create build directories" >&2; exit 1; }

# Build the flatpak
echo "Building flatpak package..."
flatpak run org.flatpak.Builder --disable-rofiles-fuse --user --force-clean build-dir com.github.yafti.gtk.yml --repo=repo

# Export the flatpak bundle
echo "Exporting flatpak bundle..."
flatpak build-bundle repo yafti-gtk.flatpak com.github.yafti.gtk

# Verify bundle was created
if [ ! -f yafti-gtk.flatpak ]; then
    echo "Error: flatpak bundle not found after export. Expected 'yafti-gtk.flatpak'" >&2
    exit 1
fi

echo ""
echo "✓ Build complete!"
echo "✓ Flatpak bundle exported: yafti-gtk.flatpak"
echo ""
echo "To test the app:"
echo "  flatpak run com.github.yafti.gtk"
echo ""
echo "To install the bundle on another system:"
echo "  flatpak install yafti-gtk.flatpak"
