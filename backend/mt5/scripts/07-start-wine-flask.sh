#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "07-start-wine-flask.sh"

# Start custom application or script if configured
if [ -n "$CUSTOM_COMMAND" ]; then
    log_message "INFO" "Starting custom command in background: $CUSTOM_COMMAND"
    eval "$CUSTOM_COMMAND" &
elif [ -n "$CUSTOM_SCRIPT" ]; then
    log_message "INFO" "Starting custom script in Wine Python: $CUSTOM_SCRIPT"
    wine python "$CUSTOM_SCRIPT" &
fi

# Determine if original Flask API should run (default: true if no custom app specified, otherwise false)
if [ -z "$ENABLE_FLASK_API" ]; then
    if [ -n "$CUSTOM_COMMAND" ] || [ -n "$CUSTOM_SCRIPT" ]; then
        ENABLE_FLASK_API="false"
    else
        ENABLE_FLASK_API="true"
    fi
fi

if [ "$ENABLE_FLASK_API" = "true" ]; then
    log_message "INFO" "Starting Flask server in Wine environment..."
    wine python /app/app.py &
    FLASK_PID=$!
    sleep 5
    if ps -p $FLASK_PID > /dev/null; then
        log_message "INFO" "Flask server in Wine started successfully with PID $FLASK_PID."
    else
        log_message "WARNING" "Failed to start Flask server in Wine."
    fi
else
    log_message "INFO" "Original Flask API disabled (ENABLE_FLASK_API=$ENABLE_FLASK_API)."
fi