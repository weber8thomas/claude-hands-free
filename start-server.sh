#!/bin/bash
# Quick start script for Claude Voice Server

set -e

echo "╔══════════════════════════════════════════╗"
echo "║   Starting Claude Voice Server          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    exit 1
fi

# Check dependencies
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

# Check services
echo "🔍 Checking services..."

# Whisper
if ! curl -s http://localhost:10300/ &>/dev/null; then
    echo "⚠️  Whisper not running on port 10300"
    echo "    Start with: cd ../whisper && docker-compose up -d"
fi

# Piper
if ! curl -s http://localhost:10200/ &>/dev/null; then
    echo "⚠️  Piper not running on port 10200"
    echo "    Start with: cd ../piper && docker-compose up -d"
fi

# Claude CLI
if ! command -v claude &> /dev/null; then
    echo "⚠️  Claude Code CLI not found"
    echo "    Install from: https://claude.com/claude-code"
fi

echo ""
echo "✅ Starting server on http://0.0.0.0:8765"
echo ""

# Start server
python3 server.py
