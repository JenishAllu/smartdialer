from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import os
from app.services.engine import Engine
from app.services.dataset import summary, borrower_rows

app = FastAPI(title="SmartDialer", version="1.0.0", description="Safe progressive/predictive dialing prototype using the supplied synthetic dataset.")
engine = Engine()
DATASET = Path(os.getenv("DATASET_DIR", "collections_30k_dataset"))

class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    team: str = "T1"
class BorrowerIn(BaseModel):
    borrower_id: str
    name: str
    phone: str
    priority: int = 5
class CampaignIn(BaseModel):
    name: str = "Demo campaign"
    mode: str = "progressive"
    provider: str = "A"
class DialIn(BaseModel):
    requested_calls: int | None = None
    answer_rate: float | None = Field(default=None, ge=0, le=1)
    avg_talk_seconds: int = Field(default=120, ge=1, le=7200)
class EventIn(BaseModel):
    event_id: str
    call_id: str
    event_type: str

@app.get("/")
def root():
    return {"name":"SmartDialer","status":"running","docs":"/docs","dataset":"/dataset/summary"}
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/dataset/summary")
def dataset_summary():
    try: return summary(DATASET)
    except Exception as e: raise HTTPException(500, str(e))
@app.get("/dataset/borrowers")
def preview_borrowers(limit: int = 20):
    try: return borrower_rows(DATASET, max(1,min(limit,500)))
    except Exception as e: raise HTTPException(500,str(e))
@app.post("/dataset/import-borrowers")
def import_borrowers(limit: int = 100):
    try:
        rows = borrower_rows(DATASET,max(1,min(limit,5000)))
        added = sum(engine.add_borrower(r["borrower_id"],r["name"],r["phone"],r["priority"],"dataset") for r in rows)
        return {"imported":added,"examined":len(rows),"queue_size":len(engine.state["borrowers"])}
    except Exception as e: raise HTTPException(500,str(e))
@app.post("/agents")
def add_agent(x: AgentIn): return engine.add_agent(x.name,x.team)
@app.get("/agents")
def agents(): return list(engine.state["agents"].values())
@app.patch("/agents/{agent_id}/status")
def agent_status(agent_id: str, status: str):
    try: return engine.set_agent_status(agent_id,status.upper())
    except KeyError: raise HTTPException(404,"Agent not found")
    except ValueError as e: raise HTTPException(409,str(e))
@app.post("/borrowers")
def add_borrower(x: BorrowerIn):
    try:
        if not engine.add_borrower(x.borrower_id,x.name,x.phone,x.priority): raise HTTPException(409,"Borrower already exists")
        return {"borrower_id":x.borrower_id,"status":"QUEUED"}
    except ValueError as e: raise HTTPException(400,str(e))
@app.get("/borrowers")
def borrowers(): return list(engine.state["borrowers"].values())
@app.post("/campaigns")
def create_campaign(x: CampaignIn):
    try: return engine.create_campaign(x.name,x.mode.lower(),x.provider.upper())
    except ValueError as e: raise HTTPException(400,str(e))
@app.get("/campaigns")
def campaigns(): return list(engine.state["campaigns"].values())
@app.post("/campaigns/{campaign_id}/dial")
def dial(campaign_id: str,x: DialIn):
    try: return engine.dial(campaign_id,x.requested_calls,x.answer_rate,x.avg_talk_seconds)
    except KeyError: raise HTTPException(404,"Campaign not found")
    except ValueError as e: raise HTTPException(400,str(e))
@app.get("/calls")
def calls(): return list(engine.state["calls"].values())
@app.post("/providers/{provider}/events")
def provider_event(provider: str,x: EventIn):
    try: return engine.process_event(provider.upper(),x.event_id,x.call_id,x.event_type.upper())
    except KeyError: raise HTTPException(404,"Call not found")
    except ValueError as e: raise HTTPException(400,str(e))
@app.post("/simulation/run")
def simulation(agents: int=10, borrowers: int=100, mode: str="predictive", answer_rate: float=.4, avg_talk_seconds: int=120, provider: str="B"):
    try: return engine.simulation(agents,borrowers,mode,answer_rate,avg_talk_seconds,provider.upper())
    except ValueError as e: raise HTTPException(400,str(e))
@app.get("/metrics")
def metrics(): return engine.metrics()
@app.post("/admin/reset")
def reset(): engine.reset(); return {"status":"reset"}
