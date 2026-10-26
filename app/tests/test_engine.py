from app.services.engine import Engine

def make(tmp_path): return Engine(tmp_path / "state.json")

def test_progressive_capacity(tmp_path):
    e=make(tmp_path)
    for i in range(3): e.add_agent(f"A{i}")
    for i in range(10): e.add_borrower(f"B{i}",f"Borrower{i}",f"900000{i:04d}")
    c=e.create_campaign("test","progressive","A")
    result=e.dial(c["campaign_id"],answer_rate=0)
    assert result["calls_started"] <= 3
    assert result["safety_approved"] <= 3

def test_duplicate_event(tmp_path):
    e=make(tmp_path); e.add_agent("A"); e.add_borrower("B1","Borrower","9000000000")
    c=e.create_campaign("test","progressive","A")
    r=e.dial(c["campaign_id"],answer_rate=0)
    call_id=r["call_ids"][0]
    assert e.process_event("A","event-1",call_id,"FAILED")["duplicate"] is False
    assert e.process_event("A","event-1",call_id,"FAILED")["duplicate"] is True

def test_terminal_call_not_resurrected(tmp_path):
    e=make(tmp_path); e.add_agent("A"); e.add_borrower("B1","Borrower","9000000000")
    c=e.create_campaign("test","progressive","A")
    r=e.dial(c["campaign_id"],answer_rate=0)
    call_id=r["call_ids"][0]
    e.process_event("A","failed",call_id,"FAILED")
    e.process_event("A","late",call_id,"RINGING")
    assert next(x for x in e.state["calls"].values() if x["call_id"]==call_id)["status"] == "FAILED"

def test_connected_call_ignores_late_ringing_event(tmp_path):
    e=make(tmp_path); e.add_agent("A"); e.add_borrower("B1","Borrower","9000000000")
    c=e.create_campaign("test","progressive","A")
    call_id=e.dial(c["campaign_id"],answer_rate=1)["call_ids"][0]
    e.process_event("A","answered",call_id,"ANSWERED")
    result=e.process_event("A","late-ringing",call_id,"RINGING")
    assert result["status"] == "CONNECTED"

def test_provider_cannot_update_another_provider_call(tmp_path):
    e=make(tmp_path); e.add_agent("A"); e.add_borrower("B1","Borrower","9000000000")
    c=e.create_campaign("test","progressive","A")
    call_id=e.dial(c["campaign_id"],answer_rate=1)["call_ids"][0]
    try:
        e.process_event("B","wrong-provider",call_id,"COMPLETED")
    except ValueError as exc:
        assert str(exc) == "provider does not own call"
    else:
        raise AssertionError("wrong provider event was accepted")

def test_restart_marks_connected_call_for_reconciliation(tmp_path):
    state_file=tmp_path / "state.json"
    e=Engine(state_file); e.add_agent("A"); e.add_borrower("B1","Borrower","9000000000")
    c=e.create_campaign("test","progressive","A")
    call_id=e.dial(c["campaign_id"],answer_rate=1)["call_ids"][0]
    restarted=Engine(state_file)
    assert restarted.state["calls"][call_id]["needs_reconciliation"] is True
