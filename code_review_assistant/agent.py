"""
Main agent orchestration for the Code Review Assistant.

This module defines a comprehensive code review assistant that analyzes
Python code and provides detailed feedback through a multi-stage pipeline.
"""

from google.adk.agents import Agent, SequentialAgent
from code_review_assistant.sub_agents.review_pipeline.code_analyzer import code_analyzer_agent
from code_review_assistant.sub_agents.review_pipeline.style_checker import style_checker_agent
from code_review_assistant.sub_agents.review_pipeline.test_runner import test_runner_agent
from code_review_assistant.sub_agents.review_pipeline.feedback_synthesizer import feedback_synthesizer_agent

from google.adk.agents import Agent
from .config import config

# Create sequential pipeline
code_review_pipeline = SequentialAgent(
    name="CodeReviewPipeline",
    description="Complete code review pipeline with analysis, testing, and feedback",
    sub_agents=[
        code_analyzer_agent,
        style_checker_agent,
        test_runner_agent,
        feedback_synthesizer_agent
    ]
)

# Root agent - coordinates the review pipeline
root_agent = Agent(
    name="CodeReviewAssistant",
    model=config.worker_model,
    description="An intelligent code review assistant that analyzes Python code and provides educational feedback",
    instruction="""You are a specialized Python code review assistant focused on helping developers improve their code quality.

When a user provides Python code for review:
1. Immediately delegate to CodeReviewPipeline and pass the code EXACTLY as it was provided by the user.
2. The pipeline will handle all analysis and feedback
3. Return ONLY the final feedback from the pipeline - do not add any commentary

When a user asks what you can do or asks general questions:
- Explain your capabilities for code review
- Do NOT trigger the pipeline for non-code messages

The pipeline handles everything for code review - just pass through its final output.""",
    sub_agents=[code_review_pipeline],
    output_key="assistant_response"
)

# MODULE_6_STEP_5_CREATE_FIX_LOOP


# MODULE_6_STEP_5_UPDATE_ROOT_AGENT
