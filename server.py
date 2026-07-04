"""
Server — FastAPI backend for the Ollama Cyber Defense Dashboard.

Integrates all components:
- Serves the static frontend (HTML/CSS/JS)
- WebSocket endpoint for real-time dashboard updates
- REST API for controlling the simulation and agent
- Alert simulator running in background
- ReAct agent processing alerts autonomously

Run with:
    python server.py
"""

import asyncio
import json
import logging
import os
import datetime
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from alert_simulator import generate_alert, generate_scenario_alert, ATTACK_SCENARIOS
from react_agent import ReActAgent
from cyber_tools import get_action_log, get_firewall_rules

# ─── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── WebSocket Manager ─────────────────────────────────────
class ConnectionManager:
    """Manages WebSocket connections and broadcasts events to all clients."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast an event to all connected WebSocket clients."""
        message = json.dumps({"type": event_type, "data": data, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.remove(conn)


manager = ConnectionManager()


# ─── Global State ──────────────────────────────────────────
class SimulationState:
    def __init__(self):
        self.is_running: bool = False
        self.scenario: str = "mixed"
        self.interval: float = 8.0  # seconds between alerts
        self.task: Optional[asyncio.Task] = None
        self.agent: Optional[ReActAgent] = None
        self.alerts_history: list[dict] = []
        self.results_history: list[dict] = []
        self.model_name: str = "hf.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M"

    def get_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "scenario": self.scenario,
            "interval": self.interval,
            "model": self.model_name,
            "alerts_count": len(self.alerts_history),
            "results_count": len(self.results_history),
            "agent_stats": self.agent.get_stats() if self.agent else {},
        }


sim_state = SimulationState()


# ─── Agent Event Callback ─────────────────────────────────
async def agent_event_callback(event_type: str, data: dict):
    """Forward agent events to all WebSocket clients."""
    await manager.broadcast(event_type, data)


# ─── Simulation Loop ──────────────────────────────────────
async def simulation_loop():
    """Background task that generates alerts and feeds them to the ReAct agent."""
    logger.info(f"Simulation started — scenario: {sim_state.scenario}, interval: {sim_state.interval}s")

    while sim_state.is_running:
        try:
            # Generate an alert
            alert = generate_scenario_alert(sim_state.scenario)
            sim_state.alerts_history.append(alert)

            # Broadcast the raw alert to dashboard
            await manager.broadcast("new_alert", alert)

            # Process with ReAct agent
            if sim_state.agent:
                result = await sim_state.agent.process_alert(alert)
                sim_state.results_history.append(result)

            # Wait before next alert
            await asyncio.sleep(sim_state.interval)

        except asyncio.CancelledError:
            logger.info("Simulation cancelled")
            break
        except Exception as e:
            logger.error(f"Simulation error: {e}")
            await asyncio.sleep(2)

    logger.info("Simulation stopped")


# ─── Detect available Ollama models ───────────────────────
async def detect_ollama_model() -> str:
    """Find the best available chat model in Ollama."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:11434/api/tags", timeout=5)
            data = resp.json()
            models = data.get("models", [])

            # Prefer instruction-tuned / chat models, skip embedding models
            for m in models:
                name = m.get("name", "")
                family = m.get("details", {}).get("family", "")
                # Skip embedding models
                if "embed" in name.lower() or "embed" in family.lower():
                    continue
                logger.info(f"Selected Ollama model: {name}")
                return name

            if models:
                return models[0]["name"]
    except Exception as e:
        logger.warning(f"Could not detect Ollama models: {e}")

    return "hf.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M"


# ─── FastAPI App ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # Detect model
    sim_state.model_name = await detect_ollama_model()
    logger.info(f"Using Ollama model: {sim_state.model_name}")

    # Initialize agent
    sim_state.agent = ReActAgent(
        model_name=sim_state.model_name,
        event_callback=agent_event_callback,
    )

    yield

    # Shutdown
    if sim_state.task and not sim_state.task.done():
        sim_state.task.cancel()


app = FastAPI(
    title="Ollama Cyber Defense Dashboard",
    description="Autonomous Cyber Incident Response Using Reasoning and Action",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Static Files ─────────────────────────────────────────
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/{filename}")
async def serve_static(filename: str):
    filepath = os.path.join(STATIC_DIR, filename)
    if os.path.exists(filepath) and not os.path.isdir(filepath):
        return FileResponse(filepath)
    return JSONResponse({"error": "Not found"}, status_code=404)


# ─── WebSocket Endpoint ───────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        await websocket.send_text(json.dumps({
            "type": "init",
            "data": sim_state.get_status(),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }))

        while True:
            # Listen for client commands
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                await handle_ws_command(msg, websocket)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": "Invalid JSON"},
                }))
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def handle_ws_command(msg: dict, websocket: WebSocket):
    """Handle commands from WebSocket clients."""
    cmd = msg.get("command")

    if cmd == "start_simulation":
        sim_state.scenario = msg.get("scenario", "mixed")
        sim_state.interval = msg.get("interval", 8.0)
        await start_simulation()

    elif cmd == "stop_simulation":
        await stop_simulation()

    elif cmd == "manual_alert":
        # Process a single alert manually
        alert = generate_scenario_alert(msg.get("scenario", "mixed"))
        sim_state.alerts_history.append(alert)
        await manager.broadcast("new_alert", alert)
        if sim_state.agent:
            result = await sim_state.agent.process_alert(alert)
            sim_state.results_history.append(result)

    elif cmd == "get_status":
        await websocket.send_text(json.dumps({
            "type": "status",
            "data": sim_state.get_status(),
        }))

    elif cmd == "change_model":
        new_model = msg.get("model", sim_state.model_name)
        sim_state.model_name = new_model
        sim_state.agent = ReActAgent(
            model_name=new_model,
            event_callback=agent_event_callback,
        )
        await manager.broadcast("model_changed", {"model": new_model})


# ─── REST API Endpoints ───────────────────────────────────
class SimulationConfig(BaseModel):
    scenario: str = "mixed"
    interval: float = 8.0


@app.get("/api/status")
async def api_status():
    """Get current system status."""
    return sim_state.get_status()


@app.post("/api/simulation/start")
async def api_start_simulation(config: SimulationConfig):
    """Start the alert simulation."""
    sim_state.scenario = config.scenario
    sim_state.interval = config.interval
    await start_simulation()
    return {"status": "started", "scenario": config.scenario, "interval": config.interval}


@app.post("/api/simulation/stop")
async def api_stop_simulation():
    """Stop the alert simulation."""
    await stop_simulation()
    return {"status": "stopped"}


@app.get("/api/alerts")
async def api_get_alerts():
    """Get alert history."""
    return {"alerts": sim_state.alerts_history[-50:]}  # Last 50


@app.get("/api/results")
async def api_get_results():
    """Get processing results history."""
    return {"results": sim_state.results_history[-20:]}  # Last 20


@app.get("/api/firewall")
async def api_get_firewall():
    """Get current firewall rules."""
    return {"rules": get_firewall_rules()}


@app.get("/api/action-log")
async def api_get_action_log():
    """Get full action audit log."""
    return {"log": get_action_log()}


@app.get("/api/scenarios")
async def api_get_scenarios():
    """Get available attack scenarios."""
    scenarios = {}
    for key, val in ATTACK_SCENARIOS.items():
        scenarios[key] = {
            "name": val["name"],
            "description": val["description"],
        }
    return {"scenarios": scenarios}


@app.post("/api/manual-alert")
async def api_manual_alert(scenario: str = "mixed"):
    """Generate and process a single alert manually."""
    alert = generate_scenario_alert(scenario)
    sim_state.alerts_history.append(alert)
    await manager.broadcast("new_alert", alert)

    result = None
    if sim_state.agent:
        result = await sim_state.agent.process_alert(alert)
        sim_state.results_history.append(result)

    return {"alert": alert, "result": result}


# ─── Helpers ───────────────────────────────────────────────
async def start_simulation():
    """Start the simulation background task."""
    if sim_state.is_running:
        return

    sim_state.is_running = True
    sim_state.task = asyncio.create_task(simulation_loop())
    await manager.broadcast("simulation_started", {
        "scenario": sim_state.scenario,
        "interval": sim_state.interval,
    })
    logger.info("Simulation started")


async def stop_simulation():
    """Stop the simulation background task."""
    sim_state.is_running = False
    if sim_state.task and not sim_state.task.done():
        sim_state.task.cancel()
        try:
            await sim_state.task
        except asyncio.CancelledError:
            pass
    await manager.broadcast("simulation_stopped", {})
    logger.info("Simulation stopped")


# ─── Entry Point ──────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 60)
    logger.info("  Ollama Cyber Defense Dashboard")
    logger.info("  Autonomous Cyber Incident Response Using ReAct")
    logger.info("=" * 60)
    logger.info("  Dashboard: http://localhost:8000")
    logger.info("  WebSocket: ws://localhost:8000/ws")
    logger.info("  API Docs:  http://localhost:8000/docs")
    logger.info("=" * 60)

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
