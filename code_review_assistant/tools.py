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


async def check_code_style(code: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Checks code style compliance using pycodestyle (PEP 8).

    Args:
        code: Python source code to check (or will retrieve from state)
        tool_context: ADK tool context

    Returns:
        Dictionary containing style score and issues
    """
    logger.info("Tool: Checking code style...")

    try:
        # Retrieve code from state if not provided
        if not code:
            code = tool_context.state.get(StateKeys.CODE_TO_REVIEW, '')
            if not code:
                return {
                    "status": "error",
                    "message": "No code provided or found in state"
                }

        # Run style check in thread pool
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(
                executor, _perform_style_check, code
            )

        # Store results in state
        tool_context.state[StateKeys.STYLE_SCORE] = result['score']
        tool_context.state[StateKeys.STYLE_ISSUES] = result['issues']
        tool_context.state[StateKeys.STYLE_ISSUE_COUNT] = result['issue_count']

        logger.info(f"Tool: Style check complete - Score: {result['score']}/100, "
                    f"Issues: {result['issue_count']}")

        return result

    except Exception as e:
        error_msg = f"Style check failed: {str(e)}"
        logger.error(f"Tool: {error_msg}", exc_info=True)

        # Set default values on error
        tool_context.state[StateKeys.STYLE_SCORE] = 0
        tool_context.state[StateKeys.STYLE_ISSUES] = []

        return {
            "status": "error",
            "message": error_msg,
            "score": 0
        }


def _perform_style_check(code: str) -> Dict[str, Any]:
    """Helper to perform style check in thread pool."""
    import io
    import sys

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        # Capture stdout to get pycodestyle output
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()

        style_guide = pycodestyle.StyleGuide(
            quiet=False,  # We want output
            max_line_length=100,
            ignore=['E501', 'W503']
        )

        result = style_guide.check_files([tmp_path])

        # Restore stdout
        sys.stdout = old_stdout

        # Parse captured output
        output = captured_output.getvalue()
        issues = []

        for line in output.strip().split('\n'):
            if line and ':' in line:
                parts = line.split(':', 4)
                if len(parts) >= 4:
                    try:
                        issues.append({
                            'line': int(parts[1]),
                            'column': int(parts[2]),
                            'code': parts[3].split()[0] if len(parts) > 3 else 'E000',
                            'message': parts[3].strip() if len(parts) > 3 else 'Unknown error'
                        })
                    except (ValueError, IndexError):
                        pass

        # Add naming convention checks
        try:
            tree = ast.parse(code)
            naming_issues = _check_naming_conventions(tree)
            issues.extend(naming_issues)
        except SyntaxError:
            pass  # Syntax errors will be caught elsewhere

        # Calculate weighted score
        score = _calculate_style_score(issues)

        return {
            "status": "success",
            "score": score,
            "issue_count": len(issues),
            "issues": issues[:10],  # First 10 issues
            "summary": f"Style score: {score}/100 with {len(issues)} violations"
        }

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _check_naming_conventions(tree: ast.AST) -> List[Dict[str, Any]]:
    """Check PEP 8 naming conventions."""
    naming_issues = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Skip private/protected methods and __main__
            if not node.name.startswith('_') and node.name != node.name.lower():
                naming_issues.append({
                    'line': node.lineno,
                    'column': node.col_offset,
                    'code': 'N802',
                    'message': f"N802 function name '{node.name}' should be lowercase"
                })
        elif isinstance(node, ast.ClassDef):
            # Check if class name follows CapWords convention
            if not node.name[0].isupper() or '_' in node.name:
                naming_issues.append({
                    'line': node.lineno,
                    'column': node.col_offset,
                    'code': 'N801',
                    'message': f"N801 class name '{node.name}' should use CapWords convention"
                })

    return naming_issues


def _calculate_style_score(issues: List[Dict[str, Any]]) -> int:
    """Calculate weighted style score based on violation severity."""
    if not issues:
        return 100

    # Define weights by error type
    weights = {
        'E1': 10,  # Indentation errors
        'E2': 3,  # Whitespace errors
        'E3': 5,  # Blank line errors
        'E4': 8,  # Import errors
        'E5': 5,  # Line length
        'E7': 7,  # Statement errors
        'E9': 10,  # Syntax errors
        'W2': 2,  # Whitespace warnings
        'W3': 2,  # Blank line warnings
        'W5': 3,  # Line break warnings
        'N8': 7,  # Naming conventions
    }

    total_deduction = 0
    for issue in issues:
        code_prefix = issue['code'][:2] if len(issue['code']) >= 2 else 'E2'
        weight = weights.get(code_prefix, 3)
        total_deduction += weight

    # Cap at 100 points deduction
    return max(0, 100 - min(total_deduction, 100))


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
