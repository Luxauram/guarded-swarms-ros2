#!/usr/bin/env python3
# ==============================================================================
# Copyright 2026 Luca D'Aurizio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Report generation for resilience test results.

Supports terminal output and JSON export for archiving.
"""

import json
import time
from pathlib import Path

from framework.base_test import TestSuite


def save_report(suite: TestSuite, output_dir: str = "results"):
    """Export a completed TestSuite to a timestamped JSON report file.

    The generated report contains scenario metadata, aggregate pass/fail
    statistics, and the full list of recorded TestResult objects. Reports are
    intended for archival, CI integration, regression tracking, and post-test
    analysis. If the output directory does not exist, it is created
    automatically.

    Example output filename:
        results/resilience_forged_tokens_20260112_143210.json

    @param suite       Completed TestSuite instance containing all results
                       collected during a resilience test scenario.
    @param output_dir  Directory where the JSON report will be written.
                       Defaults to "results".
    @return            Path of the generated report file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{output_dir}/resilience_{suite.scenario}_{timestamp}.json"
    report = {
        "scenario": suite.scenario,
        "timestamp": timestamp,
        "total": len(suite.results),
        "passed": suite.passed(),
        "failed": suite.failed(),
        "all_passed": suite.all_passed(),
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "duration_s": r.duration_s,
                "details": r.details,
            }
            for r in suite.results
        ],
    }
    with open(filename, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to: {filename}")
    return filename