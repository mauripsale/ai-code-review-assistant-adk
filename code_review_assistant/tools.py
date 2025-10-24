"""
Tools for the Code Review Assistant.

These tools provide safe code analysis, style checking, test generation,
and feedback management capabilities using ADK's built-in code executor.
"""

import ast
import asyncio
import hashlib
import json
import os
import pycodestyle
import tempfile
import logging
from datetime import datetime
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from google.genai import types
from google.adk.tools import ToolContext

from .constants import StateKeys

# Configure logging
logger = logging.getLogger(__name__)


async def analyze_code_structure(code: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Analyzes Python code structure using AST parsing.

    This tool parses Python code to extract structural information
    including functions, classes, imports, and complexity metrics.

    Args:
        code: Python source code to analyze
        tool_context: ADK tool context for state management

    Returns:
        Dictionary containing analysis results and status
    """
    logger.info("Tool: Analyzing code structure...")

    try:
        # Validate input
        if not code or not isinstance(code, str):
            return {
                "status": "error",
                "message": "No code provided or invalid input"
            }

        # Parse in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            tree = await loop.run_in_executor(executor, ast.parse, code)

            # Extract comprehensive structural information
            analysis = await loop.run_in_executor(
                executor, _extract_code_structure, tree, code
        )

                # Store code and analysis for other agents to access
        tool_context.state[StateKeys.CODE_TO_REVIEW] = code
        tool_context.state[StateKeys.CODE_ANALYSIS] = analysis
        tool_context.state[StateKeys.CODE_LINE_COUNT] = len(code.splitlines())

        logger.info(f"Tool: Analysis complete - {analysis['metrics']['function_count']} functions, "
                    f"{analysis['metrics']['class_count']} classes")

        return {
            "status": "success",
            "analysis": analysis,
            "summary": f"Found {analysis['metrics']['function_count']} functions and "
                       f"{analysis['metrics']['class_count']} classes"
        }

    except SyntaxError as e:
        error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
        logger.error(f"Tool: {error_msg}")
        tool_context.state[StateKeys.CODE_TO_REVIEW] = code
        tool_context.state[StateKeys.SYNTAX_ERROR] = error_msg

        return {
            "status": "error",
            "error_type": "syntax",
            "message": error_msg,
            "line": e.lineno,
            "offset": e.offset
        }
    except Exception as e:
        error_msg = f"Analysis failed: {str(e)}"
        logger.error(f"Tool: {error_msg}", exc_info=True)

        return {
            "status": "error",
            "error_type": "parse",
            "message": error_msg
        }


def _extract_code_structure(tree: ast.AST, code: str) -> Dict[str, Any]:
    """
    Helper function to extract structural information from AST.
    Runs in thread pool for CPU-bound work.
    """
    functions = []
    classes = []
    imports = []
    docstrings = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_info = {
                'name': node.name,
                'args': [arg.arg for arg in node.args.args],
                'lineno': node.lineno,
                'has_docstring': ast.get_docstring(node) is not None,
                'is_async': isinstance(node, ast.AsyncFunctionDef),
                'decorators': [d.id for d in node.decorator_list
                               if isinstance(d, ast.Name)]
            }
            functions.append(func_info)

            if func_info['has_docstring']:
                docstrings.append(f"{node.name}: {ast.get_docstring(node)[:50]}...")

        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)

            class_info = {
                'name': node.name,
                'lineno': node.lineno,
                'methods': methods,
                'has_docstring': ast.get_docstring(node) is not None,
                'base_classes': [base.id for base in node.bases
                                 if isinstance(base, ast.Name)]
            }
            classes.append(class_info)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    'module': alias.name,
                    'alias': alias.asname,
                    'type': 'import'
                })
        elif isinstance(node, ast.ImportFrom):
            imports.append({
                'module': node.module or '',
                'names': [alias.name for alias in node.names],
                'type': 'from_import',
                'level': node.level
            })

    return {
        'functions': functions,
        'classes': classes,
        'imports': imports,
        'docstrings': docstrings,
        'metrics': {
            'line_count': len(code.splitlines()),
            'function_count': len(functions),
            'class_count': len(classes),
            'import_count': len(imports),
            'has_main': any(f['name'] == 'main' for f in functions),
            'has_if_main': '__main__' in code,
            'avg_function_length': _calculate_avg_function_length(tree)
        }
    }


def _calculate_avg_function_length(tree: ast.AST) -> float:
    """Calculate average function length in lines."""
    function_lengths = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
                length = node.end_lineno - node.lineno + 1
                function_lengths.append(length)

    if function_lengths:
        return sum(function_lengths) / len(function_lengths)
    return 0.0


# MODULE_5_STEP_1_STYLE_CHECKER_TOOL


# MODULE_5_STEP_1_STYLE_HELPERS


# MODULE_5_STEP_4_SEARCH_PAST_FEEDBACK


# MODULE_5_STEP_4_UPDATE_GRADING_PROGRESS


# MODULE_5_STEP_4_SAVE_GRADING_REPORT


# MODULE_6_STEP_3_VALIDATE_FIXED_STYLE


# MODULE_6_STEP_3_COMPILE_FIX_REPORT


# MODULE_6_STEP_3_EXIT_FIX_LOOP


# MODULE_6_STEP_6_SAVE_FIX_REPORT


# Module exports
__all__ = [
    'analyze_code_structure',
    'check_code_style',
    'search_past_feedback',
    'update_grading_progress',
    'save_grading_report',
    'validate_fixed_style',
    'compile_fix_report',
    'save_fix_report',
]
