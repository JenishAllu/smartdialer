import json, os, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from app.services.providers import provider_for
from app.services.safety import SafetyController

AGENT_STATUSES = {"AVAILABLE", "RESERVED", "DIALING", "CONNECTED", "WRAP_UP", "OFFLINE", "PAUSED"}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
EVENT_MAP = {"INITIATED":"INITIATED", "RINGING":"RINGING", "ANSWERED":"CONNECTED", "CONNECTED":"CONNECTED",
             "COMPLETED":"COMPLETED", "FAILED":"FAILED", "NO_ANSWER":"FAILED", "BUSY":"FAILED", "CANCELLED":"CANCELLED"}
CALL_STATE_RANK = {"RESERVED": 1, "INITIATED": 2, "RINGING": 3, "CONNECTED": 4,
                   "COMPLETED": 5, "FAILED": 5, "CANCELLED": 5}
def stamp(): return datetime.now(timezone.utc).isoformat()

class Engine:
    """Single-process prototype. Use PostgreSQL transactions/row locks for multi-worker deployment."""
    def __init__(self, state_file=None):
        self.path = Path(state_file or os.getenv("SMARTDIALER_STATE_FILE", "smartdialer_state.json"))
        self.lock = threading.RLock()
        self.safety = SafetyController()
        self.state = self.empty()
        if self.path.exists():
            try: self.state = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception: self.state = self.empty()
        self.state.setdefault("provider_health", {"A": {"consecutive_timeouts": 0}, "B": {"consecutive_timeouts": 0}})
        self.recover_inflight_calls()

    @staticmethod
    def empty():
        return {"agents": {}, "borrowers": {}, "campaigns": {}, "calls": {}, "events": {},
            "provider_health": {"A": {"consecutive_timeouts": 0}, "B": {"consecutive_timeouts": 0}}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def reset(self):
        with self.lock:
            self.state = self.empty()
            self.save()

    def recover_inflight_calls(self):
        """Make a restart explicit: uncertain provider calls await reconciliation."""
        changed = False
        for call in self.state["calls"].values():
            if call.get("status") in {"RESERVED", "INITIATED", "RINGING", "CONNECTED"}:
                if call.get("status") == "RESERVED":
                    self.release(call, "FAILED")
                else:
                    call["needs_reconciliation"] = True
                changed = True
        if changed:
            self.save()

    def add_agent(self, name, team="T1"):
        with self.lock:
            aid = "AG-" + uuid.uuid4().hex[:8]
            obj = {"agent_id": aid, "name": name, "team": team, "status": "AVAILABLE", "current_call_id": None}
            self.state["agents"][aid] = obj; self.save(); return obj

    def set_agent_status(self, aid, status):
        if status not in AGENT_STATUSES: raise ValueError("Invalid agent status")
        with self.lock:
            a = self.state["agents"].get(aid)
            if not a: raise KeyError(aid)
            if a["current_call_id"] and status in {"AVAILABLE", "OFFLINE", "PAUSED"}:
                raise ValueError("Agent has an active call reservation")
            a["status"] = status; self.save(); return a

    def add_borrower(self, bid, name, phone, priority=5, source="manual"):
        bid, phone = str(bid).strip(), str(phone).strip()
        if not bid or not phone: raise ValueError("borrower_id and phone are required")
        with self.lock:
            if bid in self.state["borrowers"]: return False
            self.state["borrowers"][bid] = {"borrower_id":bid, "name":name or "Unknown", "phone":phone,
                "priority":max(1,min(10,int(priority))), "status":"QUEUED", "source":source, "created_at":stamp()}
            self.save(); return True

    def create_campaign(self, name, mode="progressive", provider="A"):
        if mode not in {"progressive", "predictive"}: raise ValueError("mode must be progressive or predictive")
        if provider not in {"A", "B"}: raise ValueError("provider must be A or B")
        with self.lock:
            cid = "CMP-" + uuid.uuid4().hex[:8]
            c = {"campaign_id":cid, "name":name, "mode":mode, "provider":provider, "status":"ACTIVE"}
            self.state["campaigns"][cid] = c; self.save(); return c

    def release(self, call, status):
        call["status"], call["updated_at"] = status, stamp()
        a = self.state["agents"].get(call["agent_id"])
        b = self.state["borrowers"].get(call["borrower_id"])
        if a and a.get("current_call_id") == call["call_id"]:
            a["current_call_id"], a["status"] = None, "AVAILABLE"
        if b and b["status"] == "RESERVED":
            b["status"] = "CONTACTED" if status == "COMPLETED" else "QUEUED"

    def dial(self, cid, requested_calls=None, answer_rate=None, avg_talk_seconds=120):
        with self.lock:
            campaign = self.state["campaigns"].get(cid)
            if not campaign: raise KeyError(cid)
            available = [a for a in self.state["agents"].values() if a["status"] == "AVAILABLE" and not a["current_call_id"]]
            queue = sorted([b for b in self.state["borrowers"].values() if b["status"] == "QUEUED"], key=lambda b:(-b["priority"],b["created_at"]))
            active = [c for c in self.state["calls"].values() if c["status"] not in TERMINAL]
            observed = [c for c in self.state["calls"].values() if c.get("outcome") in {"ANSWERED","NO_ANSWER","BUSY","FAILED"}]
            observed_rate = sum(c["outcome"] == "ANSWERED" for c in observed) / len(observed) if observed else .35
            rate = observed_rate if answer_rate is None else float(answer_rate)
            connected = sum(c["status"] == "CONNECTED" for c in active)
            ringing = sum(c["status"] in {"INITIATED","RINGING"} for c in active)
            if campaign["mode"] == "progressive":
                recommendation = len(available)
            else:
                # Conservative, transparent heuristic; it is only a recommendation.
                recommendation = min(len(available) * 2, int(len(available) / max(rate, .1))) if available else 0
            if requested_calls is not None: recommendation = min(recommendation, max(0, int(requested_calls)))
            provider = provider_for(campaign["provider"])
            provider_health = self.state["provider_health"].setdefault(campaign["provider"], {"consecutive_timeouts": 0})
            safe_count, safety_reason = self.safety.approve(
                recommendation, available, queue,
                provider_healthy=provider_health["consecutive_timeouts"] < 3,
            )
            started, answered, failed, timeouts = [], 0, 0, 0
            for agent, borrower in zip(available[:safe_count], queue[:safe_count]):
                call_id = "CALL-" + uuid.uuid4().hex[:10]
                # Reserve both agent and borrower before provider invocation.
                agent["status"], agent["current_call_id"] = "RESERVED", call_id
                borrower["status"] = "RESERVED"
                call = {"call_id":call_id,"campaign_id":cid,"agent_id":agent["agent_id"],"borrower_id":borrower["borrower_id"],
                        "status":"RESERVED","provider":campaign["provider"],"provider_call_id":None,"created_at":stamp(),
                        "updated_at":stamp(),"outcome":None,"needs_reconciliation":False}
                self.state["calls"][call_id] = call
                result = provider.initiate_call(rate)
                if result["timeout"]:
                    call["status"], call["needs_reconciliation"] = "INITIATED", True
                    provider_health["consecutive_timeouts"] += 1
                    agent["status"] = "DIALING"; timeouts += 1; started.append(call_id); continue
                provider_health["consecutive_timeouts"] = 0
                call["provider_call_id"], call["status"] = result["provider_call_id"], "INITIATED"
                agent["status"] = "DIALING"
                call["outcome"] = result["outcome"]
                if result["outcome"] == "ANSWERED":
                    call["status"], agent["status"], borrower["status"] = "CONNECTED", "CONNECTED", "CONTACTED"
                    answered += 1
                else:
                    self.release(call, "FAILED"); failed += 1
                if result.get("duplicate_event"):
                    self.event(f"{call_id}:dup", call, "INITIATED")
                if result.get("out_of_order"):
                    self.event(f"{call_id}:late", call, "RINGING")
                started.append(call_id)
            self.save()
            return {"campaign_id":cid,"mode":campaign["mode"],"available_agents_before":len(available),
                    "queued_borrowers_before":len(queue),"connected_calls_before":connected,"ringing_calls_before":ringing,
                    "observed_answer_rate":round(observed_rate,3),"answer_rate_used":round(rate,3),
                    "pacing_recommendation":recommendation,"safety_approved":safe_count,"safety_reason":safety_reason,
                    "calls_started":len(started),"calls_answered":answered,"calls_failed":failed,"provider_timeouts":timeouts,
                    "call_ids":started,"avg_talk_seconds_assumption":avg_talk_seconds}

    def event(self, event_id, call, event_type):
        if event_id in self.state["events"]: return {"duplicate":True,"status":call["status"]}
        self.state["events"][event_id] = {"event_id":event_id,"call_id":call["call_id"],"event_type":event_type,"received_at":stamp()}
        target = EVENT_MAP[event_type]
        if call["status"] not in TERMINAL and CALL_STATE_RANK[target] >= CALL_STATE_RANK.get(call["status"], 0):
            call["status"] = target
            call["updated_at"] = stamp()
        return {"duplicate":False,"status":call["status"]}

    def process_event(self, provider, event_id, call_id, event_type):
        if provider not in {"A","B"}: raise ValueError("provider must be A or B")
        if event_type not in EVENT_MAP: raise ValueError(f"Unsupported event type: {event_type}")
        with self.lock:
            call = self.state["calls"].get(call_id)
            if not call: raise KeyError(call_id)
            if call["provider"] != provider: raise ValueError("provider does not own call")
            result = self.event(event_id, call, event_type)
            if event_type in {"COMPLETED","FAILED","NO_ANSWER","BUSY","CANCELLED"}: self.release(call, EVENT_MAP[event_type])
            elif call["status"] == "CONNECTED":
                a = self.state["agents"].get(call["agent_id"])
                b = self.state["borrowers"].get(call["borrower_id"])
                if a: a["status"] = "CONNECTED"
                if b: b["status"] = "CONTACTED"
            self.save(); return result

    def simulation(self, agents, borrowers, mode, answer_rate, avg_talk_seconds, provider):
        if not 1 <= agents <= 1000 or not 1 <= borrowers <= 10000: raise ValueError("agents 1..1000; borrowers 1..10000")
        if not 0 <= answer_rate <= 1: raise ValueError("answer_rate must be 0..1")
        if mode not in {"progressive","predictive"}: raise ValueError("mode must be progressive or predictive")
        self.reset()
        for i in range(agents): self.add_agent(f"Simulation Agent {i+1}", "SIM")
        for i in range(borrowers): self.add_borrower(f"SIM-BRW-{i+1}", f"Borrower {i+1}", f"900000{i+1:04d}")
        c = self.create_campaign("Simulation", mode, provider)
        result = self.dial(c["campaign_id"], answer_rate=answer_rate, avg_talk_seconds=avg_talk_seconds)
        result["metrics"] = self.metrics()
        result["note"] = "Synthetic one-cycle simulation; no real calls are placed."
        return result

    def metrics(self):
        calls, agents, borrowers = list(self.state["calls"].values()), list(self.state["agents"].values()), list(self.state["borrowers"].values())
        return {"agents_total":len(agents),"agents_available":sum(a["status"]=="AVAILABLE" for a in agents),
                "agents_busy":sum(bool(a["current_call_id"]) for a in agents),"borrowers_total":len(borrowers),
                "borrowers_queued":sum(b["status"]=="QUEUED" for b in borrowers),"calls_total":len(calls),
                "calls_connected":sum(c["status"]=="CONNECTED" for c in calls),
                "calls_needing_reconciliation":sum(bool(c.get("needs_reconciliation")) for c in calls),
                "provider_events_seen":len(self.state["events"]),
                "safety_violations":sum(c["status"]=="CONNECTED" and not c.get("agent_id") for c in calls)}
