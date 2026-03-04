"""
TDD agent mode — write, test, fix, repeat.
"""
import re
import subprocess
from pathlib import Path
from utils.logger import info, warning, separator
from core.display import (
    show_tdd_status, show_tdd_failure,
    show_tdd_complete, show_shell, show_response, show_error
)

MAX_TDD_ITERATIONS = 5

class TestResult:
    def __init__(self, passed, failed, errors, output, failures):
        self.passed = passed
        self.failed = failed
        self.errors = errors
        self.output = output
        self.failures = failures  # list of (test_name, error_text)
        self.total = passed + failed + errors
        self.all_pass = failed == 0 and errors == 0

def run_tests(test_path):
    """Run pytest and parse results."""
    result = subprocess.run(
        ['python3', '-m', 'pytest', str(test_path), '-v', '--tb=short', '--no-header'],
        capture_output=True, text=True, timeout=60
    )
    output = result.stdout + result.stderr
    return parse_pytest_output(output)

def parse_pytest_output(output):
    """Extract pass/fail counts and failure details from pytest output."""
    passed = len(re.findall(r' PASSED', output))
    failed = len(re.findall(r' FAILED', output))
    errors = len(re.findall(r' ERROR', output))
    # Extract individual failure details
    failures = []
    # Match FAILED test names
    fail_names = re.findall(r'FAILED (\S+)', output)
    # Match short tracebacks
    blocks = re.split(r'_{5,}', output)
    for block in blocks:
        if 'FAILED' in block or 'AssertionError' in block or 'Error' in block:
            name_match = re.search(r'(test_\w+|\w+::test_\w+)', block)
            name = name_match.group(1) if name_match else 'unknown test'
            failures.append((name, block.strip()[:600]))
    if not failures and fail_names:
        for name in fail_names:
            failures.append((name, 'See output above'))
    return TestResult(passed, failed, errors, output, failures)

def find_test_file(source_path):
    """Find or suggest a test file for a source file."""
    p = Path(source_path)
    candidates = [
        p.parent / f'test_{p.name}',
        p.parent / f'{p.stem}_test{p.suffix}',
        p.parent / 'tests' / f'test_{p.name}',
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None

def build_fix_prompt(source_path, source_code, test_path, failures, iteration):
    """Build a targeted prompt for fixing failing tests."""
    failure_text = ''
    for name, error in failures[:3]:  # max 3 failures to stay in context
        failure_text += f'\nFAILED: {name}\n{error[:300]}\n'
    return (
        f'Fix {Path(source_path).name} so the failing tests pass.\n\n'
        f'Failing tests:{failure_text}\n'
        f'Current {Path(source_path).name}:\n```python\n{source_code}\n```\n\n'
        f'Rewrite {Path(source_path).name} to fix ONLY the failing tests. '
        f'Do not break passing tests. Use write_file.'
    )

def build_generate_prompt(source_path, test_path, test_code):
    """Build prompt to write initial implementation from tests."""
    return (
        f'Write {Path(source_path).name} to make these tests pass.\n\n'
        f'Tests in {Path(test_path).name}:\n```python\n{test_code}\n```\n\n'
        f'Write a complete implementation. Use write_file.'
    )

def run_tdd_loop(source_path, test_path, yolo=True):
    """
    Main TDD loop:
    1. Run tests
    2. If fail: ask model to fix
    3. Repeat until pass or MAX_TDD_ITERATIONS
    """
    from core.agent import run_agent
    from core.context import load_file
    from utils import config as _cfg
    _cfg.AGENT_CONFIG['confirm_write'] = False
    _cfg.AGENT_CONFIG['confirm_shell'] = False
    source_p = Path(source_path)
    test_p   = Path(test_path)
    if not test_p.exists():
        show_error(f'Test file not found: {test_path}')
        return
    test_code = test_p.read_text()
    history = []
    # If source doesn't exist yet, generate it from tests
    if not source_p.exists():
        info(f'Generating {source_p.name} from tests...')
        load_file(str(test_p))
        prompt = build_generate_prompt(source_path, test_path, test_code)
        _, history = run_agent(prompt, history, yolo=True)
        # Verify file was actually written with content
        if not source_p.exists() or source_p.stat().st_size < 10:
            show_error(f"{source_p.name} was not created or is empty. Retrying...")
            _, history = run_agent(
                f"You must create {source_p.name} using write_file with actual Python code. "
                f"The file does not exist yet. Write the implementation now.",
                history, yolo=True
            )
    # TDD loop
    for iteration in range(1, MAX_TDD_ITERATIONS + 1):
        info(f'Running tests — iteration {iteration}/{MAX_TDD_ITERATIONS}...')
        result = run_tests(test_path)
        show_tdd_status(iteration, MAX_TDD_ITERATIONS,
                        result.passed, result.failed + result.errors, result.total)
        show_shell(f'pytest {test_p.name} -v', result.output,
                   error=not result.all_pass)
        if result.all_pass and result.total > 0:
            show_tdd_complete(result.passed, result.total, iteration)
            show_response(
                f'All {result.total} tests pass. '
                f'{source_p.name} is complete after {iteration} iteration(s).'
            )
            return
        if iteration == MAX_TDD_ITERATIONS:
            break
        # Show failures and ask model to fix
        for name, error in result.failures[:2]:
            show_tdd_failure(name, error)
        if source_p.exists():
            source_code = source_p.read_text()
            load_file(str(source_p))
        else:
            source_code = ''
        fix_prompt = build_fix_prompt(
            source_path, source_code, test_path,
            result.failures, iteration
        )
        _, history = run_agent(fix_prompt, history, yolo=True)
    # Exhausted iterations
    show_tdd_complete(result.passed, result.total, MAX_TDD_ITERATIONS)
    show_error(f'{result.failed + result.errors} test(s) still failing after {MAX_TDD_ITERATIONS} iterations.')
