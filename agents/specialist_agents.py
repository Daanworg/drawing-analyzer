# in drawing_analyzer/agents/specialist_agents.py

from google.adk.agents import LlmAgent
from .prompts import AGENT_PROMPTS

def create_cognitive_dispatcher_agent():
    """
    Creates and returns the Cognitive Dispatcher agent.
    This agent analyzes an image of a drawing and creates a JSON work plan.
    """
    return LlmAgent(
        # We use a powerful Gemini model because it has a large
        # context window and excellent vision/JSON capabilities.
        model="gemini-2.5-flash",
        name="Cognitive_Dispatcher",
        instruction=AGENT_PROMPTS["Cognitive_Dispatcher"],
    )

def create_specialist_agent(agent_name: str) -> LlmAgent:
    """
    Generic factory for creating any specialist agent based on its name.
    The agent's instructions are pulled from the AGENT_PROMPTS dictionary.
    """
    if agent_name not in AGENT_PROMPTS:
        raise ValueError(f"Prompt for agent '{agent_name}' not found in AGENT_PROMPTS.")

    return LlmAgent(
        model="gemini-2.5-flash",
        name=agent_name,
        instruction=AGENT_PROMPTS[agent_name],
    )

# --- Final Synthesizer Agent ---

def create_chief_engineer_agent():
    """Creates the Chief_Engineer agent."""
    return LlmAgent(
        model="gemini-2.5-flash",
        name="Chief_Engineer",
        instruction=AGENT_PROMPTS["Chief_Engineer"],
    )
