"""
Multi-Agent ReAct System — LangGraph implementation.

Implements the multi-agent architecture:
1. Triage Agent: Evaluates severity and routes.
2. Analyst Agent: Investigates low/medium threats.
3. Mitigation Agent: Executes containment actions (UFW, Docker isolation).

Uses LangChain with Ollama and LangGraph's StateGraph.
"""

import json
import re
import logging
import datetime
from typing import Any, Callable, Optional, TypedDict, Literal

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END

from cyber_tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

# --- State Definition ---
class AgentState(TypedDict):
    alert: dict
    alert_id: str
    messages: list
    steps: list
    final_status: str
    next_agent: str


# --- Prompts ---
TRIAGE_PROMPT = """You are the TRIAGE AGENT in a SOC multi-agent system.
Analyze the following Wazuh/Suricata alert and decide the immediate next step.

Alert severity levels are: low, medium, high, critical.
Categories: port_scan, brute_force, botnet, etc.

Rules:
- If severity is 'critical' or 'high', or category is 'botnet' or 'brute_force', you must route to MITIGATION immediately.
- If severity is 'medium' or 'low', route to ANALYST for investigation.
- If it's a known false positive, route to END.

Respond EXACTLY in this format:
Thought: [Your reasoning]
Next: [MITIGATION or ANALYST or END]
"""

ANALYST_PROMPT = """You are the THREAT ANALYST AGENT.
Investigate the alert using available tools to determine if it's a real threat.

Available tools:
- analyze_traffic: {"source_ip": "IP", "dest_ip": "IP", "dest_port": PORT}
- check_vulnerability: {"port": PORT, "service": "service_name"}

Respond EXACTLY in this format:
Thought: [Your reasoning]
Action: [tool_name or 'finish' if you have concluded]
Action Input: {"param": "value"}

When finished investigating, set Action to 'finish' and provide a Next routing.
If it's a real threat, route to MITIGATION. If benign, route to END.
Example finish:
Thought: The traffic analysis shows it's a false positive.
Action: finish
Next: END
"""

MITIGATION_PROMPT = """You are the MITIGATION AGENT.
Take active measures to contain the threat based on the alert and any previous analysis.

Available tools:
- execute_ufw: {"action": "deny", "source_ip": "IP"}
- isolate_host: {"host_ip": "IP", "reason": "reason for isolation"}

CRITICAL RULES:
- When using isolate_host, the parameter MUST be exactly "host_ip", NEVER "host_id".

Respond EXACTLY in this format:
Thought: [Your reasoning]
Action: [tool_name or 'finish']
Action Input: {"param": "value"}

When finished mitigating, set Action to 'finish'.
Example finish:
Thought: The IP has been blocked. Threat contained.
Action: finish
Next: END
"""


def _fuzzy_parse(text: str, expect_next: bool = False) -> dict:
    """Parse the LLM output. Extracts Thought, Action, Action Input, and Next."""
    result = {
        "thought": "No reasoning provided.",
        "action": None,
        "action_input": {},
        "next": "END"
    }
    
    logger.info(f"Fuzzy parsing text:\n{text}")
    
    thought_match = re.search(r"(?:\*+)?Thought(?:\*+)?:\s*(.*?)(?=\n(?:\*+)?(?:Action|Next)(?:\*+)?:|$)", text, re.IGNORECASE | re.DOTALL)
    if thought_match:
        result["thought"] = thought_match.group(1).strip()
    else:
        fallback_match = re.search(r"(.*?)(?=\n(?:\*+)?(?:Action|Next)(?:\*+)?:|$)", text, re.IGNORECASE | re.DOTALL)
        if fallback_match and fallback_match.group(1).strip():
            result["thought"] = fallback_match.group(1).strip()
        else:
            result["thought"] = text.strip() or "No reasoning provided."
        
    action_match = re.search(r"(?:\*+)?Action(?:\*+)?:\s*([a-zA-Z0-9_]+)", text, re.IGNORECASE)
    if action_match:
        extracted = action_match.group(1).strip().lower()
        if extracted in ["analyze_traffic", "check_vulnerability", "execute_ufw", "isolate_host", "finish"]:
            result["action"] = extracted
        else:
            result["action"] = "finish"
        
    input_match = re.search(r"(?:\*+)?Action\s*Input(?:\*+)?:\s*({.*})", text, re.IGNORECASE | re.DOTALL)
    if input_match:
        try:
            raw_input = json.loads(input_match.group(1).strip())
            result["action_input"] = {k.lower(): v for k, v in raw_input.items()}
        except:
            # Fallback simple parsing
            pairs = re.findall(r'["\']?(\w+)["\']?\s*[:=]\s*["\']?([^"\'}\s,]+)["\']?', input_match.group(1))
            for k, v in pairs:
                k_lower = k.lower()
                try:
                    result["action_input"][k_lower] = int(v)
                except:
                    result["action_input"][k_lower] = v

    next_match = re.search(r"(?:\*+)?Next(?:\*+)?:\s*([a-zA-Z]+)", text, re.IGNORECASE)
    if next_match:
        result["next"] = next_match.group(1).strip().upper()
        
    return result


class MultiAgentSystem:
    """
    LangGraph-based Multi-Agent system for cyber response.
    """

    def __init__(
        self,
        model_name: str = "hf.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        event_callback: Optional[Callable] = None,
    ):
        self.model_name = model_name
        self.event_callback = event_callback
        
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
            num_predict=2048,
        )

        self.stats = {
            "alerts_processed": 0,
            "actions_executed": 0,
            "ips_blocked": 0,
            "hosts_isolated": 0,
            "total_reasoning_steps": 0,
        }
        
        self.graph = self._build_graph()
        logger.info(f"LangGraph Multi-Agent initialized with: {model_name}")

    async def _emit(self, event_type: str, data: dict):
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.error(f"Error emitting event: {e}")

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("triage", self.triage_node)
        workflow.add_node("analyst", self.analyst_node)
        workflow.add_node("mitigation", self.mitigation_node)

        # Routing edges
        workflow.add_conditional_edges(
            "triage",
            lambda x: x["next_agent"],
            {
                "MITIGATION": "mitigation",
                "ANALYST": "analyst",
                "END": END
            }
        )
        
        workflow.add_conditional_edges(
            "analyst",
            lambda x: x["next_agent"],
            {
                "MITIGATION": "mitigation",
                "ANALYST": "analyst", # loop to itself if more actions needed
                "END": END
            }
        )

        workflow.add_conditional_edges(
            "mitigation",
            lambda x: x["next_agent"],
            {
                "MITIGATION": "mitigation", # loop to itself if more actions needed
                "END": END
            }
        )

        workflow.set_entry_point("triage")
        return workflow.compile()

    # --- Nodes ---

    async def triage_node(self, state: AgentState) -> AgentState:
        """Triage agent node."""
        self.stats["total_reasoning_steps"] += 1
        await self._emit("reasoning_start", {"alert_id": state["alert_id"], "step": len(state["steps"])+1, "status": "thinking", "agent": "TRIAGE"})
        
        alert_json = json.dumps(state["alert"], indent=2)
        prompt = f"{TRIAGE_PROMPT}\n\nAlert:\n```json\n{alert_json}\n```"
        
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            logger.info(f"TRIAGE LLM OUTPUT:\n{response.content}")
            parsed = _fuzzy_parse(response.content)
            next_agent = parsed.get("next", "MITIGATION") # default to mitigation on fail
            if next_agent not in ["MITIGATION", "ANALYST", "END"]:
                next_agent = "MITIGATION"
                
            thought = parsed.get("thought", response.content)
            
        except Exception as e:
            # Fallback rule
            severity = state["alert"].get("severity", "medium")
            if severity in ("critical", "high"):
                next_agent = "MITIGATION"
                thought = "Critical severity. Immediate mitigation required."
            else:
                next_agent = "ANALYST"
                thought = "Medium severity. Routing to analyst."

        await self._emit("reasoning_step", {
            "alert_id": state["alert_id"],
            "step": len(state["steps"])+1,
            "agent": "TRIAGE",
            "thought": thought,
            "action": f"Route to {next_agent}",
            "action_input": {}
        })

        state["steps"].append({"agent": "TRIAGE", "thought": thought, "routed_to": next_agent})
        state["next_agent"] = next_agent
        return state

    async def analyst_node(self, state: AgentState) -> AgentState:
        """Analyst agent node."""
        self.stats["total_reasoning_steps"] += 1
        step_num = len(state["steps"])+1
        await self._emit("reasoning_start", {"alert_id": state["alert_id"], "step": step_num, "status": "thinking", "agent": "ANALYST"})
        
        # Build context
        context = f"Alert:\n{json.dumps(state['alert'], indent=2)}\n\nPrevious steps:\n"
        for s in state["steps"]:
            context += f"- {s}\n"
            
        messages = [SystemMessage(content=ANALYST_PROMPT)] + state["messages"] + [HumanMessage(content=context)]
        
        try:
            response = self.llm.invoke(messages)
            parsed = _fuzzy_parse(response.content)
        except Exception:
            # Fallback
            parsed = {"thought": "Investigation complete. Passing to mitigation.", "action": "finish", "next": "MITIGATION", "action_input": {}}
            
        action = parsed.get("action", "finish")
        thought = parsed.get("thought", "")
        next_agent = parsed.get("next", "MITIGATION")
        
        action_input = parsed.get("action_input", {})
        if action and action.lower() != "finish":
            # Prevent duplicate actions (loop breaking)
            is_duplicate = any(
                s.get("action") == action and s.get("action_input") == action_input
                for s in state["steps"]
            )
            if is_duplicate:
                action = "finish"
                thought = "Action already executed. Preventing loop."
                next_agent = "END"
                
        if action and action.lower() != "finish":
            await self._execute_tool_wrapper(action, action_input, "ANALYST", state, thought, step_num)
            state["next_agent"] = "ANALYST" # Loop back for more analysis
        else:
            await self._emit("reasoning_step", {
                "alert_id": state["alert_id"],
                "step": step_num,
                "agent": "ANALYST",
                "thought": thought,
                "action": f"Finish and route to {next_agent}",
                "action_input": {}
            })
            state["next_agent"] = next_agent if next_agent in ["MITIGATION", "END"] else "END"

        state["steps"].append({"agent": "ANALYST", "thought": thought, "action": action})
        return state

    async def mitigation_node(self, state: AgentState) -> AgentState:
        """Mitigation agent node."""
        self.stats["total_reasoning_steps"] += 1
        step_num = len(state["steps"])+1
        await self._emit("reasoning_start", {"alert_id": state["alert_id"], "step": step_num, "status": "thinking", "agent": "MITIGATION"})
        
        # Build context
        context = f"Alert:\n{json.dumps(state['alert'], indent=2)}\n\nPrevious steps:\n"
        for s in state["steps"]:
            context += f"- {s}\n"
            
        messages = [SystemMessage(content=MITIGATION_PROMPT)] + state["messages"] + [HumanMessage(content=context)]
        
        try:
            response = self.llm.invoke(messages)
            parsed = _fuzzy_parse(response.content)
        except Exception:
            # Fallback block
            src_ip = state["alert"].get("data", {}).get("src_ip", "0.0.0.0")
            parsed = {"thought": "Blocking source IP to contain threat.", "action": "execute_ufw", "action_input": {"source_ip": src_ip, "action": "deny"}, "next": "END"}

        action = parsed.get("action", "finish")
        thought = parsed.get("thought", "")
        
        action_input = parsed.get("action_input", {})
        if action and action.lower() != "finish":
            # Prevent duplicate actions (loop breaking)
            is_duplicate = any(
                s.get("action") == action and s.get("action_input") == action_input
                for s in state["steps"]
            )
            if is_duplicate:
                action = "finish"
                thought = "Action already executed. Preventing loop."
                
        if action and action.lower() != "finish":
            await self._execute_tool_wrapper(action, action_input, "MITIGATION", state, thought, step_num)
            state["next_agent"] = "MITIGATION" # Loop back
        else:
            await self._emit("reasoning_step", {
                "alert_id": state["alert_id"],
                "step": step_num,
                "agent": "MITIGATION",
                "thought": thought,
                "action": "Finish Mitigation",
                "action_input": {}
            })
            state["next_agent"] = "END"
            state["final_status"] = "mitigated"
            
        state["steps"].append({"agent": "MITIGATION", "thought": thought, "action": action})
        return state

    async def _execute_tool_wrapper(self, action: str, action_input: dict, agent_name: str, state: AgentState, thought: str, step_num: int):
        """Helper to execute tool and emit events."""
        await self._emit("reasoning_step", {
            "alert_id": state["alert_id"],
            "step": step_num,
            "agent": agent_name,
            "thought": thought,
            "action": action,
            "action_input": action_input,
        })
        
        if action in TOOLS:
            self.stats["actions_executed"] += 1
            await self._emit("action_executing", {
                "alert_id": state["alert_id"],
                "tool": action,
                "arguments": action_input,
                "agent": agent_name
            })
            
            tool_result = execute_tool(action, action_input)
            
            if action == "execute_ufw":
                self.stats["ips_blocked"] += 1
            elif action == "isolate_host":
                self.stats["hosts_isolated"] += 1
                
            await self._emit("action_result", {
                "alert_id": state["alert_id"],
                "tool": action,
                "result": tool_result,
                "agent": agent_name
            })
            
            observation = f"Observation: Tool '{action}' returned: {json.dumps(tool_result)}"
            state["messages"].append(AIMessage(content=f"Action: {action}\nAction Input: {json.dumps(action_input)}"))
            state["messages"].append(HumanMessage(content=observation))
        else:
            await self._emit("action_result", {
                "alert_id": state["alert_id"],
                "tool": action,
                "result": {"status": "error", "message": "Unknown tool"},
                "agent": agent_name
            })

    async def process_alert(self, alert: dict) -> dict:
        """Entry point for processing an alert."""
        self.stats["alerts_processed"] += 1
        start_time = datetime.datetime.now(datetime.timezone.utc)
        alert_id = alert.get("id", "unknown")

        await self._emit("alert_received", {
            "alert": alert,
            "agent_status": "analyzing",
        })

        initial_state = AgentState(
            alert=alert,
            alert_id=alert_id,
            messages=[],
            steps=[],
            final_status="pending",
            next_agent="triage"
        )

        try:
            # Run the LangGraph workflow
            final_state = await self.graph.ainvoke(initial_state)
        except Exception as e:
            logger.error(f"Graph execution error: {e}")
            final_state = initial_state
            final_state["final_status"] = "error"

        if final_state.get("final_status") == "pending":
            final_state["final_status"] = "completed"

        # Generate mini summary
        steps = final_state.get("steps", [])
        triage_route = next((s.get("routed_to") for s in steps if s.get("agent") == "TRIAGE"), "Unknown")
        analyst_tools = [s["action"] for s in steps if s.get("agent") == "ANALYST" and s.get("action") and s["action"].lower() != "finish"]
        mitigation_tools = [s["action"] for s in steps if s.get("agent") == "MITIGATION" and s.get("action") and s["action"].lower() != "finish"]

        summary_parts = [f"Triage: ➔ {triage_route}"]
        if analyst_tools:
            summary_parts.append(f"Analyst: {', '.join(analyst_tools)}")
        if mitigation_tools:
            summary_parts.append(f"Mitigation: {', '.join(mitigation_tools)}")
            
        summary_text = "Resumo: " + " | ".join(summary_parts)

        await self._emit("mitigation_complete", {
            "alert_id": alert_id,
            "summary": summary_text,
            "steps_taken": len(steps),
        })

        end_time = datetime.datetime.now(datetime.timezone.utc)
        
        await self._emit("stats_update", self.stats)

        return {
            "alert_id": alert_id,
            "alert": alert,
            "steps": final_state.get("steps", []),
            "final_status": final_state.get("final_status"),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_ms": int((end_time - start_time).total_seconds() * 1000)
        }

    def get_stats(self) -> dict:
        return self.stats.copy()

# Ensure backwards compatibility for server.py import
ReActAgent = MultiAgentSystem
