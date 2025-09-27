# in drawing_analyzer/agents/orchestrator.py

import json
import re
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, InvocationContext, ParallelAgent, LlmAgent
from google.adk.events import Event
from google.genai.types import Content, Part
from pydantic import Field

from . import specialist_agents
from .prompts import AGENT_PROMPTS, ALL_AGENTS

AGENT_FACTORY = {
    agent_name: specialist_agents.create_specialist_agent
    for agent_name in ALL_AGENTS
}
AGENT_FACTORY["Cognitive_Dispatcher"] = specialist_agents.create_cognitive_dispatcher_agent
AGENT_FACTORY["Chief_Engineer"] = specialist_agents.create_chief_engineer_agent


class DrawingAnalysisOrchestrator(BaseAgent):
    name: str = "Drawing_Analysis_Orchestrator"
    dispatcher: LlmAgent = Field(default_factory=specialist_agents.create_cognitive_dispatcher_agent)
    chief_engineer: LlmAgent = Field(default_factory=specialist_agents.create_chief_engineer_agent)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        print("--- Orchestrator: Running Cognitive Dispatcher... ---")
        dispatcher_events = self.dispatcher.run_async(ctx)
        
        plan_json_str = ""
        async for event in dispatcher_events:
            if event.is_final_response() and event.content:
                plan_json_str = event.content.parts[0].text
            yield event

        try:
            if match := re.search(r"```json\s*(\{.*?\})\s*```", plan_json_str, re.DOTALL):
                plan_json_str = match.group(1)
            
            work_plan = json.loads(plan_json_str)
            agents_to_execute = work_plan.get("execution_agents", [])
            print(f"--- Orchestrator: Plan received. Executing {len(agents_to_execute)} specialist agents. ---")
        except (json.JSONDecodeError, TypeError) as e:
            error_msg = f"Orchestrator: FATAL ERROR - Could not parse plan from Dispatcher. Error: {e}. Raw output: {plan_json_str}"
            print(error_msg)
            yield Event(author=self.name, content=Content(parts=[Part(text=error_msg)]))
            return

        if agents_to_execute:
            specialist_instances = []
            for agent_name in agents_to_execute:
                if agent_name in AGENT_FACTORY:
                    agent_factory_func = AGENT_FACTORY[agent_name]
                    agent_instance = agent_factory_func(agent_name) if agent_factory_func == specialist_agents.create_specialist_agent else agent_factory_func()
                    agent_instance.output_key = f"result_{agent_name}"
                    specialist_instances.append(agent_instance)
                else:
                    print(f"--- Orchestrator WARNING: Agent '{agent_name}' not found in factory. ---")

            if specialist_instances:
                parallel_swarm = ParallelAgent(name="Specialist_Swarm", sub_agents=specialist_instances)
                swarm_events = parallel_swarm.run_async(ctx)
                async for event in swarm_events:
                    yield event
        
        print("--- Orchestrator: All specialist agents have completed. ---")
        print("--- Orchestrator: Running Chief Engineer... ---")
        
        agent_results = []
        failed_agents = []
        for agent_name in agents_to_execute:
            result_key = f"result_{agent_name}"
            raw_output = ctx.session.state.get(result_key)
            
            if raw_output is None:
                agent_results.append({"agent_name": agent_name, "output": {"error": "Agent did not produce any output."}})
                failed_agents.append(agent_name)
                continue

            try:
                if isinstance(raw_output, str):
                    if match := re.search(r"```json\s*(\{.*?\})\s*```", raw_output, re.DOTALL):
                        raw_output = match.group(1)
                
                result_data = json.loads(raw_output)
                agent_results.append({"agent_name": agent_name, "output": result_data})
            except (json.JSONDecodeError, TypeError):
                print(f"--- Orchestrator ERROR: Failed to parse JSON for agent '{agent_name}'. ---")
                agent_results.append({
                    "agent_name": agent_name,
                    "output": {"error": "Failed to parse JSON output from agent.", "raw_output": raw_output}
                })
                failed_agents.append(agent_name)

        # ** THE CORRECT APPROACH **
        # 1. Place the necessary data into the session state for the next agent.
        #    The LlmAgent's instruction prompt will read these state variables.
        ctx.session.state["plan_for_synthesis"] = work_plan.get("plan")
        # We dump the results to a JSON string because prompt templating works with strings.
        ctx.session.state["agent_results_json"] = json.dumps(agent_results, indent=2)
        ctx.session.state["failed_agents_list"] = failed_agents

        # 2. Call the Chief Engineer with the *original* context.
        #    The agent will now have access to the state we just set.
        chief_events = self.chief_engineer.run_async(ctx)
        
        async for event in chief_events:
            if event.is_final_response():
                event.author = self.name
            yield event