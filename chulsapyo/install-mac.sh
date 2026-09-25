#!/bin/bash
# Chulsapyo morning window - macOS installer
# Runs at login (RunAtLoad) and every day at 07:00 (StartCalendarInterval)
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Library/Application Support/Chulsapyo"
PLIST="$HOME/Library/LaunchAgents/com.chulsapyo.morning.plist"
mkdir -p "$DEST" "$HOME/Library/LaunchAgents"
cp "$SRC/index.html" "$SRC/content.js" "$DEST/"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.chulsapyo.morning</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/open</string><string>$DEST/index.html</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer>
  </dict>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Opens at login and daily at 07:00. (It should open once now.)"
