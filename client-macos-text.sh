#!/bin/bash
# Voice client for Claude Code CLI (Text Output)
# MacBook M1 Max - Push-to-talk with text response
# Usage: ./client-macos-text.sh <server-url>

set -e

# Configuration
SERVER_URL="${1:-http://localhost:8765}"
SESSION_FILE="$HOME/.claude-voice-session"
TEMP_DIR="/tmp/claude-voice-client"
mkdir -p "$TEMP_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check dependencies
check_deps() {
    local missing=()

    if ! command -v sox &> /dev/null; then
        missing+=("sox (install with: brew install sox)")
    fi

    if ! command -v jq &> /dev/null; then
        missing+=("jq (install with: brew install jq)")
    fi

    if ! command -v curl &> /dev/null; then
        missing+=("curl")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}❌ Missing dependencies:${NC}"
        printf '  - %s\n' "${missing[@]}"
        exit 1
    fi
}

# Load or create session
load_session() {
    if [ -f "$SESSION_FILE" ]; then
        SESSION_ID=$(cat "$SESSION_FILE")
        echo -e "${BLUE}📝 Continuing conversation (session: $SESSION_ID)${NC}"
    else
        echo -e "${YELLOW}🆕 Starting new conversation${NC}"
        SESSION_ID=""
    fi
}

# Save session
save_session() {
    echo "$1" > "$SESSION_FILE"
}

# Clear session
clear_session() {
    rm -f "$SESSION_FILE"
    echo -e "${GREEN}✨ Conversation cleared${NC}"
}

# Record audio with push-to-talk
record_audio() {
    local output_file="$1"

    echo -e "${GREEN}🎤 Recording... (Press Ctrl+C to stop)${NC}"

    # Record using sox (16kHz, mono, WAV format for Whisper)
    # Use trim 0 to force sox to finalize the header on interrupt
    sox -d -r 16000 -c 1 -b 16 "$output_file" trim 0 2>/dev/null

    echo -e "${BLUE}✅ Recording saved${NC}"
}

# Send audio and get text response
send_voice() {
    local input_file="$1"

    echo -e "${BLUE}📤 Sending to Claude...${NC}"

    # Check file size
    local file_size=$(stat -f%z "$input_file" 2>/dev/null || stat -c%s "$input_file" 2>/dev/null)
    if [ "$file_size" -lt 100 ]; then
        echo -e "${RED}❌ Recording too short${NC}"
        return 1
    fi

    # Build curl command
    local response_file="$TEMP_DIR/response.json"
    local http_code

    if [ -n "$SESSION_ID" ]; then
        http_code=$(curl -s -w "%{http_code}" --max-time 120 --connect-timeout 10 \
            --expect100-timeout 2 --no-keepalive -X POST \
            -F "audio=@$input_file" \
            -F "session_id=$SESSION_ID" \
            "$SERVER_URL/voice-text" -o "$response_file" 2>&1 | tail -1)
    else
        http_code=$(curl -s -w "%{http_code}" --max-time 120 --connect-timeout 10 \
            --expect100-timeout 2 --no-keepalive -X POST \
            -F "audio=@$input_file" \
            "$SERVER_URL/voice-text" -o "$response_file" 2>&1 | tail -1)
    fi

    # Check HTTP status
    if [ "$http_code" != "200" ]; then
        echo -e "${RED}❌ Server error (HTTP $http_code)${NC}"
        if [ -f "$response_file" ]; then
            cat "$response_file"
        fi
        return 1
    fi

    if [ ! -f "$response_file" ] || [ ! -s "$response_file" ]; then
        echo -e "${RED}❌ No response received${NC}"
        return 1
    fi

    # Check if response is JSON
    if ! jq -e . "$response_file" &>/dev/null; then
        echo -e "${RED}❌ Invalid response:${NC}"
        cat "$response_file"
        return 1
    fi

    # Extract session ID
    NEW_SESSION_ID=$(jq -r '.session_id // empty' "$response_file" 2>/dev/null)
    if [ -n "$NEW_SESSION_ID" ] && [ "$NEW_SESSION_ID" != "null" ]; then
        SESSION_ID="$NEW_SESSION_ID"
        save_session "$SESSION_ID"
    fi

    # Display transcript
    TRANSCRIPT=$(jq -r '.transcript // "null"' "$response_file" 2>/dev/null)
    if [ "$TRANSCRIPT" != "null" ] && [ -n "$TRANSCRIPT" ]; then
        echo -e "${CYAN}You said: ${NC}${TRANSCRIPT}"
        echo ""
    else
        echo -e "${YELLOW}⚠️  No speech detected${NC}"
        return 1
    fi

    # Display response
    RESPONSE=$(jq -r '.response // "null"' "$response_file" 2>/dev/null)
    if [ "$RESPONSE" != "null" ] && [ -n "$RESPONSE" ]; then
        echo -e "${GREEN}Claude:${NC}"
        echo "$RESPONSE"
    else
        echo -e "${YELLOW}⚠️  No response from Claude${NC}"
        return 1
    fi

    rm -f "$response_file"
}

# Main interaction loop
main() {
    check_deps

    echo "╔══════════════════════════════════════════╗"
    echo "║   Claude Code Voice Assistant (Text)    ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    echo "Server: $SERVER_URL"
    echo ""

    # Test server connection
    if ! curl -s --max-time 5 "$SERVER_URL/health" &>/dev/null; then
        echo -e "${RED}❌ Cannot connect to server at $SERVER_URL${NC}"
        echo "   Make sure the voice server is running"
        exit 1
    fi

    load_session

    echo ""
    echo "Commands:"
    echo "  • Press Ctrl+C while recording to send"
    echo "  • Type 'new' for new conversation"
    echo "  • Type 'quit' to exit"
    echo ""

    while true; do
        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

        # Check for special commands
        read -t 1 -p "Ready? (press Enter or type command): " cmd 2>/dev/null || cmd=""

        case "$cmd" in
            "new")
                clear_session
                SESSION_ID=""
                continue
                ;;
            "quit"|"exit")
                echo "👋 Goodbye!"
                exit 0
                ;;
        esac

        # Record audio
        INPUT_FILE="$TEMP_DIR/input_$(date +%s).wav"

        if ! record_audio "$INPUT_FILE"; then
            echo -e "${RED}❌ Recording failed${NC}"
            continue
        fi

        # Send to server and display response
        if ! send_voice "$INPUT_FILE"; then
            echo -e "${YELLOW}💡 Tip: Speak clearly and press Ctrl+C after speaking${NC}"
        fi

        # Cleanup
        rm -f "$INPUT_FILE"

        echo ""
    done
}

# Handle Ctrl+C gracefully during main loop
trap 'echo ""; echo "Use Ctrl+C during recording to send, or type quit to exit."; echo ""' INT

main "$@"
