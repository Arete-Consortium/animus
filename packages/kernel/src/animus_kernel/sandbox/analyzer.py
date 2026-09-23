"""Codebase analyzer for identifying improvement opportunities."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from animus_kernel.agents.provider_wrapper import AgentProvider

logger = logging.getLogger(__name__)


class ImprovementCategory(StrEnum):
    """Categories of code improvements."""

    REFACTORING = "refactoring"
    BUG_FIXES = "bug_fixes"
    DOCUMENTATION = "documentation"
    TEST_COVERAGE = "test_coverage"
    PERFORMANCE = "performance"
    CODE_QUALITY = "code_quality"


@dataclass
class ImprovementSuggestion:
    """A suggested improvement to the codebase."""

    id: str
    category: ImprovementCategory
    title: str
    description: str
    affected_files: list[str]
    priority: int = 3  # 1 (highest) to 5 (lowest)
    estimated_lines: int = 0
    reasoning: str = ""
    implementation_hints: str = ""


@dataclass
class AnalysisResult:
    """Result of codebase analysis."""

    suggestions: list[ImprovementSuggestion] = field(default_factory=list)
    files_analyzed: int = 0
    issues_found: int = 0
    analysis_summary: str = ""


class CodebaseAnalyzer:
    """Analyzes the Animus Kernel codebase for improvement opportunities."""

    def __init__(
        self,
        provider: AgentProvider | None = None,
        codebase_path: str | Path = ".",
        allow_self_targeting: bool = False,
    ):
        """Initialize the analyzer.

        Args:
            provider: Optional AI provider for intelligent analysis.
            codebase_path: Path to codebase root.
            allow_self_targeting: If True, the self-improve module itself
                can be analyzed and modified (recursive self-targeting).
        """
        self.provider = provider
        self.codebase_path = Path(codebase_path)
        self.allow_self_targeting = allow_self_targeting

    def analyze(
        self,
        categories: list[ImprovementCategory] | None = None,
        focus_paths: list[str] | None = None,
    ) -> AnalysisResult:
        """Analyze the codebase for improvements.

        Args:
            categories: Categories to focus on. None = all.
            focus_paths: Specific paths to analyze. None = all.

        Returns:
            Analysis result with suggestions.
        """
        suggestions = []
        files_analyzed = 0
        issues_found = 0

        # Get Python files to analyze
        if focus_paths:
            files = []
            for pattern in focus_paths:
                files.extend(self.codebase_path.glob(pattern))
        else:
            # Try src/ first, fall back to **/*.py for non-standard layouts
            files = list(self.codebase_path.glob("src/**/*.py"))
            if not files:
                files = list(self.codebase_path.glob("**/*.py"))

        for file_path in files:
            if self._should_skip_file(file_path):
                continue

            files_analyzed += 1
            file_suggestions = self._analyze_file(file_path, categories)
            suggestions.extend(file_suggestions)
            issues_found += len(file_suggestions)

        # Prioritize suggestions
        suggestions.sort(key=lambda s: (s.priority, -s.estimated_lines))

        return AnalysisResult(
            suggestions=suggestions,
            files_analyzed=files_analyzed,
            issues_found=issues_found,
            analysis_summary=f"Analyzed {files_analyzed} files, found {issues_found} improvement opportunities.",
        )

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped.

        Args:
            file_path: Path to check.

        Returns:
            True if should skip.
        """
        skip_patterns = [
            "__pycache__",
            ".git",
            ".venv",
            "node_modules",
        ]
        if not self.allow_self_targeting:
            skip_patterns.append("self_improve")
        return any(pattern in str(file_path) for pattern in skip_patterns)

    def _analyze_file(
        self,
        file_path: Path,
        categories: list[ImprovementCategory] | None,
    ) -> list[ImprovementSuggestion]:
        """Analyze a single file.

        Args:
            file_path: Path to file.
            categories: Categories to check.

        Returns:
            List of suggestions for this file.
        """
        suggestions = []
        relative_path = str(file_path.relative_to(self.codebase_path))

        try:
            content = file_path.read_text()
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return suggestions

        # Run static checks
        if not categories or ImprovementCategory.CODE_QUALITY in categories:
            suggestions.extend(self._check_code_quality(relative_path, content))

        if not categories or ImprovementCategory.DOCUMENTATION in categories:
            suggestions.extend(self._check_documentation(relative_path, content))

        if not categories or ImprovementCategory.TEST_COVERAGE in categories:
            suggestions.extend(self._check_test_coverage(relative_path, content))

        if not categories or ImprovementCategory.PERFORMANCE in categories:
            suggestions.extend(self._check_performance(relative_path, content))

        return suggestions

    def _check_code_quality(
        self,
        file_path: str,
        content: str,
    ) -> list[ImprovementSuggestion]:
        """Check for code quality issues.

        Args:
            file_path: Relative file path.
            content: File content.

        Returns:
            List of suggestions.
        """
        suggestions = []
        lines = content.split("\n")

        # Check for long functions
        function_pattern = re.compile(r"^(\s*)def\s+(\w+)\s*\(")
        current_function = None
        function_start = 0

        for i, line in enumerate(lines):
            match = function_pattern.match(line)
            if match:
                # Check previous function length
                if current_function and i - function_start > 50:
                    suggestions.append(
                        ImprovementSuggestion(
                            id=f"long_function_{file_path}_{current_function}",
                            category=ImprovementCategory.REFACTORING,
                            title=f"Long function: {current_function}",
                            description=f"Function `{current_function}` has {i - function_start} lines. Consider breaking it into smaller functions.",
                            affected_files=[file_path],
                            priority=3,
                            estimated_lines=i - function_start,
                        )
                    )

                current_function = match.group(2)
                function_start = i
                _ = len(match.group(1))  # Reserved for future indentation tracking

        # Check for TODO comments
        todo_pattern = re.compile(r"#\s*TODO[:\s](.+)", re.IGNORECASE)
        for i, line in enumerate(lines):
            match = todo_pattern.search(line)
            if match:
                suggestions.append(
                    ImprovementSuggestion(
                        id=f"todo_{file_path}_{i}",
                        category=ImprovementCategory.BUG_FIXES,
                        title=f"TODO in {file_path}:{i + 1}",
                        description=f"Unresolved TODO: {match.group(1).strip()}",
                        affected_files=[file_path],
                        priority=4,
                        estimated_lines=5,
                    )
                )

        # Check for bare except
        if "except:" in content and "except Exception" not in content:
            suggestions.append(
                ImprovementSuggestion(
                    id=f"bare_except_{file_path}",
                    category=ImprovementCategory.CODE_QUALITY,
                    title=f"Bare except in {file_path}",
                    description="Found bare `except:` clause. Consider catching specific exceptions.",
                    affected_files=[file_path],
                    priority=2,
                    estimated_lines=3,
                )
            )

        return suggestions

    def _check_documentation(
        self,
        file_path: str,
        content: str,
    ) -> list[ImprovementSuggestion]:
        """Check for documentation issues.

        Args:
            file_path: Relative file path.
            content: File content.

        Returns:
            List of suggestions.
        """
        suggestions = []

        # Check for missing module docstring
        if not content.strip().startswith('"""') and not content.strip().startswith("'''"):
            suggestions.append(
                ImprovementSuggestion(
                    id=f"missing_module_docstring_{file_path}",
                    category=ImprovementCategory.DOCUMENTATION,
                    title=f"Missing module docstring: {file_path}",
                    description="Module is missing a docstring. Add a description of the module's purpose.",
                    affected_files=[file_path],
                    priority=4,
                    estimated_lines=5,
                )
            )

        # Check for public functions without docstrings
        function_pattern = re.compile(r"^def\s+(\w+)\s*\([^)]*\)\s*(?:->.*)?:", re.MULTILINE)
        for match in function_pattern.finditer(content):
            func_name = match.group(1)
            if func_name.startswith("_"):
                continue  # Skip private functions

            # Check if next non-empty line is a docstring
            start_pos = match.end()
            remaining = content[start_pos : start_pos + 200]
            if not (remaining.strip().startswith('"""') or remaining.strip().startswith("'''")):
                suggestions.append(
                    ImprovementSuggestion(
                        id=f"missing_docstring_{file_path}_{func_name}",
                        category=ImprovementCategory.DOCUMENTATION,
                        title=f"Missing docstring: {func_name}",
                        description=f"Public function `{func_name}` is missing a docstring.",
                        affected_files=[file_path],
                        priority=4,
                        estimated_lines=5,
                    )
                )

        return suggestions

    def _check_test_coverage(
        self,
        file_path: str,
        content: str,
    ) -> list[ImprovementSuggestion]:
        """Check for test coverage issues.

        Args:
            file_path: Relative file path.
            content: File content.

        Returns:
            List of suggestions.
        """
        suggestions = []

        # Skip test files themselves
        if "test_" in file_path or "_test.py" in file_path:
            return suggestions

        # Check if corresponding test file exists
        if file_path.startswith("src/"):
            # Convert src/animus_forge/foo.py to tests/test_foo.py
            module_name = Path(file_path).stem
            potential_test = f"tests/test_{module_name}.py"
            test_path = self.codebase_path / potential_test

            if not test_path.exists():
                # Count public functions that need tests
                function_pattern = re.compile(r"^def\s+([a-z]\w*)\s*\(", re.MULTILINE)
                public_functions = [
                    m.group(1)
                    for m in function_pattern.finditer(content)
                    if not m.group(1).startswith("_")
                ]

                if public_functions:
                    suggestions.append(
                        ImprovementSuggestion(
                            id=f"missing_tests_{file_path}",
                            category=ImprovementCategory.TEST_COVERAGE,
                            title=f"Missing tests for {file_path}",
                            description=f"No test file found for {file_path}. {len(public_functions)} public functions need tests.",
                            affected_files=[file_path, potential_test],
                            priority=3,
                            estimated_lines=len(public_functions) * 20,
                            implementation_hints=f"Create {potential_test} with tests for: {', '.join(public_functions[:5])}",
                        )
                    )

        return suggestions

    def _check_performance(
        self,
        file_path: str,
        content: str,
    ) -> list[ImprovementSuggestion]:
        """Check for performance issues via AST static analysis.

        Args:
            file_path: Relative file path.
            content: File content.

        Returns:
            List of performance suggestions.
        """
        import ast

        suggestions = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return suggestions

        class PerfVisitor(ast.NodeVisitor):
            def __init__(self):
                self.loop_depth = 0
                self.function_name: str | None = None
                self.suggestions: list[ImprovementSuggestion] = []

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                old_func = self.function_name
                self.function_name = node.name
                self.generic_visit(node)
                self.function_name = old_func

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self.visit_FunctionDef(node)  # type: ignore[arg-type]

            def visit_For(self, node: ast.For) -> None:
                self._enter_loop(node)

            def visit_While(self, node: ast.While) -> None:
                self._enter_loop(node)

            def _enter_loop(self, node: ast.AST) -> None:
                old_depth = self.loop_depth
                self.loop_depth += 1

                # Nested loop detection
                if self.loop_depth >= 2:
                    line = getattr(node, "lineno", 0)
                    self.suggestions.append(
                        ImprovementSuggestion(
                            id=f"perf_nested_loop_{file_path}_{line}",
                            category=ImprovementCategory.PERFORMANCE,
                            title=f"Nested loop at {file_path}:{line}",
                            description=(
                                f"Nested loops ({self.loop_depth} levels deep) can be O(n^m). "
                                "Consider flattening, using set lookups, or vectorizing."
                            ),
                            affected_files=[file_path],
                            priority=2,
                            estimated_lines=15,
                            reasoning="Algorithmic complexity concern",
                            implementation_hints="Consider set-based lookup or itertools.product",
                        )
                    )

                self.generic_visit(node)
                self.loop_depth = old_depth

            def visit_BinOp(self, node: ast.BinOp) -> None:
                # String concatenation in loops
                if (
                    self.loop_depth > 0
                    and isinstance(node.op, ast.Add)
                    and isinstance(node.left, ast.Name)
                ):
                    # Heuristic: var + something inside a loop
                    line = getattr(node, "lineno", 0)
                    self.suggestions.append(
                        ImprovementSuggestion(
                            id=f"perf_str_concat_{file_path}_{line}",
                            category=ImprovementCategory.PERFORMANCE,
                            title=f"String concatenation in loop at {file_path}:{line}",
                            description=(
                                "String concatenation with '+' inside a loop creates "
                                "intermediate string objects. Use list.append + ''.join() "
                                "or io.StringIO instead."
                            ),
                            affected_files=[file_path],
                            priority=2,
                            estimated_lines=8,
                            reasoning="O(n^2) string building",
                            implementation_hints="Collect in list, then ''.join(list)",
                        )
                    )
                self.generic_visit(node)

            def visit_Call(self, node: ast.Call) -> None:
                # list.append in loops is fine, but list.insert(0, ...) is O(n)
                if (
                    self.loop_depth > 0
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "insert"
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == 0
                ):
                    line = getattr(node, "lineno", 0)
                    self.suggestions.append(
                        ImprovementSuggestion(
                            id=f"perf_list_insert0_{file_path}_{line}",
                            category=ImprovementCategory.PERFORMANCE,
                            title=f"list.insert(0, ...) in loop at {file_path}:{line}",
                            description=(
                                "Inserting at index 0 inside a loop is O(n) per operation. "
                                "Consider using collections.deque or appending and reversing."
                            ),
                            affected_files=[file_path],
                            priority=1,
                            estimated_lines=10,
                            reasoning="Quadratic list shifting",
                            implementation_hints="Use collections.deque.appendleft()",
                        )
                    )

                # Detect list(comprehension opportunity): for x in seq: result.append(f(x))
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append"
                    and self.loop_depth > 0
                ):
                    line = getattr(node, "lineno", 0)
                    self.suggestions.append(
                        ImprovementSuggestion(
                            id=f"perf_list_comp_{file_path}_{line}",
                            category=ImprovementCategory.PERFORMANCE,
                            title=f"List append in loop at {file_path}:{line}",
                            description=(
                                "Appending to a list inside a loop may be replaceable "
                                "with a list comprehension, which is faster and more idiomatic."
                            ),
                            affected_files=[file_path],
                            priority=4,
                            estimated_lines=5,
                            reasoning="List comprehensions are ~2x faster than append loops",
                            implementation_hints="Refactor loop body into [f(x) for x in seq]",
                        )
                    )

                self.generic_visit(node)

        visitor = PerfVisitor()
        visitor.visit(tree)
        return visitor.suggestions

    async def analyze_with_ai(
        self,
        focus_file: str | None = None,
    ) -> AnalysisResult:
        """Use AI to analyze the codebase for improvements.

        Args:
            focus_file: Optional specific file to analyze.

        Returns:
            Analysis result with AI-generated suggestions.
        """
        if not self.provider:
            logger.warning("No AI provider available, using static analysis only")
            return self.analyze()

        # First do static analysis
        static_result = self.analyze()

        # Read code to analyze
        code_samples = []
        if focus_file:
            focus_path = self.codebase_path / focus_file
            if focus_path.exists() and focus_path.is_file():
                code_samples.append((focus_file, focus_path.read_text()[:5000]))
        else:
            # Sample a few Python files from the codebase
            py_files = list(self.codebase_path.rglob("*.py"))
            for py_file in py_files[:3]:  # Limit to 3 files
                rel_path = py_file.relative_to(self.codebase_path)
                if not any(
                    part.startswith(".") or part == "__pycache__" for part in rel_path.parts
                ):
                    try:
                        code_samples.append((str(rel_path), py_file.read_text()[:3000]))
                    except Exception:
                        pass  # Non-critical fallback: skip unreadable files during AI analysis

        if not code_samples:
            return static_result

        # Build prompt for AI analysis
        code_context = "\n\n".join(f"=== {path} ===\n{code}" for path, code in code_samples)
        prompt = f"""Analyze the following Python code and suggest improvements.
Focus on: code quality, potential bugs, performance, and maintainability.

{code_context}

Return your suggestions as a JSON array with this structure:
[
  {{
    "category": "refactoring|bug_fixes|documentation|test_coverage|performance|code_quality",
    "title": "Brief title",
    "description": "Detailed description",
    "affected_files": ["file1.py"],
    "priority": 1-5,
    "reasoning": "Why this improvement matters",
    "implementation_hints": "How to implement"
  }}
]

Return ONLY the JSON array, no other text."""

        try:
            response = await self.provider.complete(
                [
                    {"role": "system", "content": "You are a code review expert."},
                    {"role": "user", "content": prompt},
                ]
            )

            # Parse AI suggestions
            ai_suggestions = self._parse_ai_suggestions(response)

            # Merge AI suggestions with static analysis
            static_result.suggestions.extend(ai_suggestions)
            logger.info(f"AI analysis added {len(ai_suggestions)} suggestions")

        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")

        return static_result

    def _parse_ai_suggestions(self, response: str) -> list[ImprovementSuggestion]:
        """Parse AI response into ImprovementSuggestion objects."""
        suggestions = []

        # Try to extract JSON from response
        try:
            # Handle markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            data = json.loads(response.strip())
            if not isinstance(data, list):
                data = [data]

            for item in data:
                try:
                    category_str = item.get("category", "code_quality").lower()
                    category = ImprovementCategory(category_str)
                except ValueError:
                    category = ImprovementCategory.CODE_QUALITY

                suggestion = ImprovementSuggestion(
                    id=f"ai-{uuid.uuid4().hex[:8]}",
                    category=category,
                    title=item.get("title", "AI Suggestion"),
                    description=item.get("description", ""),
                    affected_files=item.get("affected_files", []),
                    priority=min(5, max(1, int(item.get("priority", 3)))),
                    reasoning=item.get("reasoning", ""),
                    implementation_hints=item.get("implementation_hints", ""),
                )
                suggestions.append(suggestion)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON: {e}")

        return suggestions
