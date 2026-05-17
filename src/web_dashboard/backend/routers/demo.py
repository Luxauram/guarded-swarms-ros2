"""
Copyright 2026 Luca D'Aurizio

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

"""
@file demo.py

Demo control router for the coordination demo lifecycle.

Provides REST API endpoints for launching, stopping, and inspecting the
coordination demo process. The demo runs as an external ROS 2 launch
subprocess; this router manages its lifecycle by interacting with the OS
process tree rather than tracking a single PID, since the launch wrapper
spawns multiple child processes that must all be terminated cleanly.

Endpoints:
  POST /api/demo/start  - Kill any existing demo, reset statistics, launch new demo.
  POST /api/demo/stop   - Terminate all demo-related processes.
  GET  /api/demo/status - Query whether a demo is currently running.

@author Luca D'Aurizio
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import subprocess
import os
import logging
import signal
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["Demo Control"])

demo_process_pid = None
token_processor_instance = None


# ============================================================================
# Dependency Injection
# ============================================================================


def set_token_processor(processor):
    """
    Injects the shared TokenProcessor instance into this router.

    Must be called during application startup so that the start endpoint
    can reset statistics directly without an additional HTTP round-trip.

    @param processor: Initialized TokenProcessor instance from app.py.
    """
    global token_processor_instance
    token_processor_instance = processor
    logger.info("Token processor injected into demo router")


# ============================================================================
# Request/Response Models
# ============================================================================


class DemoConfig(BaseModel):
    """Configuration parameters for a new demo launch."""

    num_agents: int = Field(default=4, ge=1, le=4, description="Number of agents (1-4)")
    arb_mode: str = Field(
        default="priority", description="Arbitration mode: fcfs | priority | hybrid"
    )
    prio_a: int = Field(default=5, ge=0, le=10, description="Agent A priority (0-10)")
    prio_b: int = Field(default=5, ge=0, le=10, description="Agent B priority (0-10)")
    prio_c: int = Field(default=5, ge=0, le=10, description="Agent C priority (0-10)")
    prio_d: int = Field(default=5, ge=0, le=10, description="Agent D priority (0-10)")


class DemoResponse(BaseModel):
    """Generic response returned by demo lifecycle endpoints."""

    success: bool
    message: str
    pid: int | None = None


# ============================================================================
# Helper Functions (Exported for Cleanup)
# ============================================================================


def kill_existing_demo():
    """
    Terminates all running demo-related OS processes.

    Uses a two-pass strategy to maximize reliability:

    Pass 1 - locate all demo.launch.py PIDs via pgrep and send SIGTERM to
    their entire process group, followed by SIGKILL after a short grace
    period. Falls back to killing the individual PID if the process group
    cannot be obtained.

    Pass 2 - runs pkill -9 against a list of known process name patterns
    (agent_node, coordinator_node, ros2 daemon, etc.) as a safety net for
    any child processes not covered by Pass 1.

    After both passes, waits briefly and verifies via pgrep that no
    demo.launch.py instances remain. Logs a warning if survivors are
    detected. As a last resort on unexpected exceptions, issues a blanket
    pkill against "demo" and "ros2" patterns.

    This function is also called from the app.py shutdown handler to ensure
    no orphaned processes remain after the server exits.
    """
    killed_count = 0

    try:
        ps_result = subprocess.run(
            ["pgrep", "-f", "demo.launch.py"], capture_output=True, text=True, check=False
        )

        if ps_result.stdout.strip():
            pids = ps_result.stdout.strip().split("\n")
            for pid_str in pids:
                try:
                    pid = int(pid_str)
                    try:
                        pgid = os.getpgid(pid)
                        os.killpg(pgid, signal.SIGTERM)
                        time.sleep(0.2)
                        try:
                            os.killpg(pgid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        killed_count += 1
                        logger.info(f"Killed process group {pgid} (PID {pid})")
                    except (ProcessLookupError, PermissionError):
                        try:
                            os.kill(pid, signal.SIGKILL)
                            killed_count += 1
                            logger.info(f"Killed individual process {pid}")
                        except ProcessLookupError:
                            pass
                except (ValueError, ProcessLookupError) as e:
                    logger.warning(f"Could not kill PID {pid_str}: {e}")
                    continue

        process_patterns = [
            "demo.launch.py",
            "ros2 launch.*demo",
            "agent_node",
            "coordinator_node",
            "_ros2_daemon",
        ]

        for pattern in process_patterns:
            result = subprocess.run(
                ["pkill", "-9", "-f", pattern], check=False, capture_output=True
            )
            if result.returncode == 0:
                killed_count += 1

        time.sleep(0.5)

        verify = subprocess.run(
            ["pgrep", "-f", "demo.launch.py"], capture_output=True, text=True, check=False
        )

        if verify.stdout.strip():
            logger.warning(f"Some demo processes survived kill attempt: {verify.stdout.strip()}")
        else:
            logger.info(f"Successfully killed all demo processes ({killed_count} operations)")

    except Exception as e:
        logger.error(f"Error in kill_existing_demo: {e}")
        subprocess.run(["pkill", "-9", "-f", "demo"], check=False, capture_output=True)
        subprocess.run(["pkill", "-9", "-f", "ros2"], check=False, capture_output=True)


def reset_statistics_direct():
    """
    Resets token processor statistics without an HTTP round-trip.

    Invokes reset_statistics() directly on the injected processor instance.
    Failures are logged as warnings rather than raised so that a statistics
    reset failure does not prevent the demo from launching.
    """
    try:
        if token_processor_instance is not None:
            token_processor_instance.reset_statistics()
            logger.info("Statistics reset directly")
        else:
            logger.warning("Token processor not available for reset")
    except Exception as e:
        logger.warning(f"Could not reset statistics: {e}")


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/start", response_model=DemoResponse)
async def start_demo(config: DemoConfig):
    """
    Kills any running demo, resets statistics, and launches a new demo.

    Executes the following steps in order:
      1. Calls kill_existing_demo() to ensure a clean slate regardless of
         whether a previous demo is tracked in memory.
      2. Calls reset_statistics_direct() to clear accumulated metrics.
      3. Constructs a bash command that sources the ROS 2 workspace and
         invokes demo.launch.py with the supplied configuration arguments,
         redirecting output to /tmp/demo.log and backgrounding the process.
      4. Waits 1.5 seconds for the launch wrapper to spawn child processes,
         then uses pgrep to locate and cache the demo.launch.py PID.

    @param config: DemoConfig specifying the number of agents, arbitration
                   mode, and per-agent priorities.
    @return:       DemoResponse indicating success, a descriptive message,
                   and the detected PID (or None if pgrep found no match).
    @raises HTTPException: 500 if the subprocess invocation itself fails.
    """
    global demo_process_pid

    logger.info(f"Starting demo with config: {config.dict()}")

    try:
        kill_existing_demo()
        demo_process_pid = None

        reset_statistics_direct()

        bash_cmd = [
            "bash",
            "-c",
            f"source /workspace/install/setup.bash && "
            f"ros2 launch /workspace/src/tools/launch/demo.launch.py "
            f"arbitration_mode:={config.arb_mode} "
            f"priority_A:={config.prio_a} "
            f"priority_B:={config.prio_b} "
            f"priority_C:={config.prio_c} "
            f"priority_D:={config.prio_d} "
            f"num_agents:={config.num_agents} "
            f"> /tmp/demo.log 2>&1 &",
        ]

        subprocess.Popen(
            bash_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )

        time.sleep(1.5)

        try:
            ps_result = subprocess.run(
                ["pgrep", "-f", "demo.launch.py"], capture_output=True, text=True, check=False
            )
            if ps_result.stdout.strip():
                pids = ps_result.stdout.strip().split("\n")
                demo_process_pid = int(pids[0])
                logger.info(f"Demo started with PID: {demo_process_pid}")
            else:
                logger.warning("Demo PID not found")
                demo_process_pid = None
        except Exception as e:
            logger.warning(f"Could not get demo PID: {e}")
            demo_process_pid = None

        return DemoResponse(
            success=True,
            message=f"Demo started with {config.num_agents} agents in {config.arb_mode} mode",
            pid=demo_process_pid,
        )

    except Exception as e:
        logger.error(f"Failed to start demo: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start demo: {str(e)}")


@router.post("/stop", response_model=DemoResponse)
async def stop_demo():
    """
    Terminates all running demo processes.

    Delegates to kill_existing_demo() rather than relying on the cached PID,
    since the launch wrapper spawns multiple child processes that may outlive
    the tracked PID. After the kill attempt, a short pause and a pgrep
    verification confirm whether all processes were successfully terminated.

    @return: DemoResponse indicating full success or a partial failure if
             any demo processes survived the kill attempt.
    @raises HTTPException: 500 if an unexpected error occurs during teardown.
    """
    global demo_process_pid

    try:
        kill_existing_demo()
        demo_process_pid = None

        time.sleep(0.3)
        check = subprocess.run(
            ["pgrep", "-f", "demo.launch.py"], capture_output=True, text=True, check=False
        )

        if check.stdout.strip():
            logger.warning("Some demo processes still running after kill attempt")
            return DemoResponse(
                success=False, message="Demo stop partially failed - some processes still running"
            )

        logger.info("Demo stopped successfully - all processes terminated")

        return DemoResponse(success=True, message="Demo stopped successfully")

    except Exception as e:
        logger.error(f"Failed to stop demo: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop demo: {str(e)}")


@router.get("/status")
async def get_demo_status():
    """
    Returns the current demo running state by querying the OS process table.

    Always uses pgrep rather than the cached PID to reflect the true system
    state, even if the cached value has become stale due to a crash or
    external termination. Updates the cached PID as a side effect when a
    running process is found.

    @return: Dictionary containing 'running' (bool), 'pid' (int or None),
             and 'process_count' (int). On error, 'running' is False and
             an 'error' key contains the exception message.
    """
    global demo_process_pid

    try:
        check = subprocess.run(
            ["pgrep", "-f", "demo.launch.py"], capture_output=True, text=True, check=False
        )

        if check.stdout.strip():
            pids = check.stdout.strip().split("\n")
            pid = int(pids[0])
            demo_process_pid = pid

            return {"running": True, "pid": pid, "process_count": len(pids)}
        else:
            demo_process_pid = None
            return {"running": False, "pid": None, "process_count": 0}

    except Exception as e:
        logger.error(f"Error checking demo status: {e}")
        return {"running": False, "pid": None, "error": str(e)}
