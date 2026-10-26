# State machines

Agent: OFFLINE/PAUSED -> AVAILABLE -> RESERVED -> DIALING -> CONNECTED -> WRAP_UP -> AVAILABLE.

Call: QUEUED -> RESERVED -> INITIATED -> RINGING -> ANSWERED/CONNECTED -> COMPLETED. Failure and cancellation are terminal outcomes. Duplicate event IDs are ignored, late events cannot regress a call, and in-flight calls are marked for reconciliation after restart.
