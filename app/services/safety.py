class SafetyController:
    """Deterministic gate between pacing recommendations and call allocation."""

    def approve(self, recommendation, available_agents, queued_borrowers, provider_healthy=True):
        if not provider_healthy:
            return 0, "provider_unhealthy"
        recommendation = max(0, int(recommendation))
        capacity = min(len(available_agents), len(queued_borrowers))
        approved = min(recommendation, capacity)
        reason = "approved" if approved == recommendation else "capped_by_agent_or_queue_capacity"
        return approved, reason
