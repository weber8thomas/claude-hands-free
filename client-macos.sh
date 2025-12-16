#!/bin/bash
# Voice client for Claude Code CLI
# MacBook M1 Max - Push-to-talk recording and playback
# Usage: ./client-macos.sh <server-url>

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
NC='\033[0m' # No Color

# Check dependencies
check_deps() {
    local missing=()

    if ! command -v sox &> /dev/null; then
        missing+=("sox (install with: brew install sox)")
    fi

    if ! command -v curl &> /dev/null; then
        missing+=("curl")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo "❌ Missing dependencies:"
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
    sox -d -r 16000 -c 1 -b 16 "$output_file" 2>/dev/null

    echo -e "${BLUE}✅ Recording saved${NC}"
}

# Send audio and get response
send_voice() {
    local input_file="$1"
    local output_file="$2"

    echo -e "${BLUE}📤 Sending to Claude...${NC}"

    # Build curl command
    local curl_cmd="curl -s -X POST"

    # Add session ID if we have one
    if [ -n "$SESSION_ID" ]; then
        curl_cmd="$curl_cmd -F session_id=$SESSION_ID"
    fi

    # Send audio file and save response
    curl_cmd="$curl_cmd -F audio=@$input_file"
    curl_cmd="$curl_cmd -D $TEMP_DIR/headers.txt"
    curl_cmd="$curl_cmd -o $output_file"
    curl_cmd="$curl_cmd $SERVER_URL/voice"

    eval "$curl_cmd"

    # Extract session ID from response headers
    if [ -f "$TEMP_DIR/headers.txt" ]; then
        NEW_SESSION_ID=$(grep -i "X-Session-ID:" "$TEMP_DIR/headers.txt" | cut -d' ' -f2 | tr -d '\r\n')
        if [ -n "$NEW_SESSION_ID" ]; then
            SESSION_ID="$NEW_SESSION_ID"
            save_session "$SESSION_ID"
        fi
    fi

    if [ ! -f "$output_file" ] || [ ! -s "$output_file" ]; then
        echo -e "${YELLOW}❌ No response received${NC}"
        return 1
    fi

    echo -e "${GREEN}✅ Response received${NC}"
}

# Play audio response
play_audio() {
    local audio_file="$1"

    echo -e "${BLUE}🔊 Playing response...${NC}"

    # Use native macOS audio player
    afplay "$audio_file"

    echo -e "${GREEN}✅ Playback complete${NC}"
}

# Main interaction loop
main() {
    check_deps

    echo "╔══════════════════════════════════════════╗"
    echo "║   Claude Code Voice Assistant (macOS)   ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    echo "Server: $SERVER_URL"
    echo ""

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
        OUTPUT_FILE="$TEMP_DIR/output_$(date +%s).wav"

        if ! record_audio "$INPUT_FILE"; then
            echo "❌ Recording failed"
            continue
        fi

        # Send to server
        if ! send_voice "$INPUT_FILE" "$OUTPUT_FILE"; then
            echo "❌ Failed to get response"
            rm -f "$INPUT_FILE"
            continue
        fi

        # Play response
        play_audio "$OUTPUT_FILE"

        # Cleanup
        rm -f "$INPUT_FILE" "$OUTPUT_FILE"

        echo ""
    done
}

# Handle Ctrl+C gracefully
trap 'echo ""; echo "Use Ctrl+C during recording to send, or type quit to exit."; echo ""' INT

main "$@"
