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
@file makefile.py

Makefile command execution router.

Provides REST API endpoints for executing whitelisted Makefile targets
from the web dashboard. Implements command validation, workspace isolation,
execution timeout, and detailed result reporting.

Security model:
  - Only commands present in settings.ALLOWED_MAKE_COMMANDS are permitted.
  - subprocess is invoked with shell=False to prevent shell injection.
  - Execution is bounded to settings.WORKSPACE_PATH.
  - A 300-second hard timeout prevents runaway processes.

Endpoints:
  GET  /api/makefile/commands - List permitted Makefile targets.
  POST /api/makefile/execute  - Execute a whitelisted target.

@author Luca D'Aurizio
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
import subprocess
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Router Configuration
# ============================================================================

router = APIRouter(prefix="/api/makefile", tags=["Build System"])

# ============================================================================
# Request/Response Models
# ============================================================================


class MakeCommandRequest(BaseModel):
    """Request body for the Makefile execution endpoint."""

    command: str = Field(
        ...,
        description="Make command to execute (must be in whitelist)",
        min_length=1,
        max_length=50,
    )

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        """
        Rejects commands containing characters that could enable shell injection.

        Checks for shell metacharacters before the whitelist lookup so that
        malformed input is refused at the model validation layer rather than
        reaching subprocess.

        @param v: Raw command string from the request body.
        @return:  Stripped command string if validation passes.
        @raises ValueError: If the command contains any forbidden character.
        """
        forbidden_chars = [";", "&", "|", "$", "`", "\n", "\r"]
        if any(char in v for char in forbidden_chars):
            raise ValueError("Command contains forbidden characters")
        return v.strip()

    class Config:
        json_schema_extra = {"example": {"command": "build"}}


class MakeCommandResponse(BaseModel):
    """Response body returned after a Makefile target execution attempt."""

    success: bool = Field(..., description="True if command executed successfully (exit code 0)")
    command: str = Field(..., description="Executed command")
    output: str = Field(..., description="Standard output from command execution")
    error: str = Field(default="", description="Standard error output (if command failed)")
    exit_code: int = Field(default=0, description="Process exit code")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "command": "build",
                "output": "Build completed successfully\n",
                "error": "",
                "exit_code": 0,
            }
        }


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/commands")
async def list_commands():
    """
    Returns the list of Makefile targets permitted by the server whitelist.

    The whitelist is defined in settings.ALLOWED_MAKE_COMMANDS. Any target
    absent from this list will be rejected by the execute endpoint.

    @return: Dictionary containing the allowed command list and the configured
             workspace path.
    """
    return {"commands": settings.ALLOWED_MAKE_COMMANDS, "workspace": settings.WORKSPACE_PATH}


@router.post("/execute", response_model=MakeCommandResponse)
async def execute_command(request: MakeCommandRequest):
    """
    Executes a whitelisted Makefile target in the configured workspace.

    Validates the requested command against the server whitelist, then
    invokes make with shell=False to prevent injection. Captures stdout
    and stderr separately and surfaces them in the response. A hard timeout
    of 300 seconds is enforced; processes that exceed it are terminated and
    a 408 error is returned.

    @param request: MakeCommandRequest containing the target name.
    @return:        MakeCommandResponse with execution result, output, and exit code.
    @raises HTTPException: 400 if the command is not in the whitelist.
    @raises HTTPException: 408 if the command exceeds the 300-second timeout.
    @raises HTTPException: 500 if the make binary is not found, the workspace
                           path is invalid, or an unexpected error occurs.
    """
    command = request.command

    if command not in settings.ALLOWED_MAKE_COMMANDS:
        logger.warning(f"Attempted to execute non-whitelisted command: {command}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Command not allowed",
                "command": command,
                "allowed_commands": settings.ALLOWED_MAKE_COMMANDS,
            },
        )

    logger.info(f"Executing make command: {command}")

    try:
        result = subprocess.run(
            ["make", command],
            cwd=settings.WORKSPACE_PATH,
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
        )

        success = result.returncode == 0

        if success:
            logger.info(f"Command '{command}' completed successfully")
        else:
            logger.warning(f"Command '{command}' failed with exit code {result.returncode}")

        return MakeCommandResponse(
            success=success,
            command=command,
            output=result.stdout,
            error=result.stderr if not success else "",
            exit_code=result.returncode,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Command '{command}' timed out after 5 minutes")
        raise HTTPException(
            status_code=408, detail=f"Command '{command}' exceeded 5 minute timeout"
        )

    except FileNotFoundError:
        logger.error(f"Make command not found or workspace path invalid: {settings.WORKSPACE_PATH}")
        raise HTTPException(
            status_code=500, detail="Make command not available or workspace path invalid"
        )

    except Exception as e:
        logger.error(f"Unexpected error executing command '{command}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute command: {str(e)}")
