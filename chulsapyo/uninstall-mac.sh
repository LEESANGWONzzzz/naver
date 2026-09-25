#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.chulsapyo.morning.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
rm -rf "$HOME/Library/Application Support/Chulsapyo"
echo "Chulsapyo removed."
