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
Guarded Swarms Coordinator Package

Token-based coordination system for multi-agent UAV swarms.
Provides secure spatial coordination with cryptographic signatures
and temporal concurrency control.

Author: Luca D'Aurizio
"""

from .token import (
    Token,
    GeometryToken,
    AuthToken,
    create_geometry_token,
    create_auth_token,
)

__version__ = "0.0.0"

__all__ = [
    "Token",
    "GeometryToken",
    "AuthToken",
    "create_geometry_token",
    "create_auth_token",
]
