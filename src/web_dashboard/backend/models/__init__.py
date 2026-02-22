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
@file __init__.py

Models package initialization.

Exports Pydantic data models for type-safe token validation, WebSocket
events, and system statistics used throughout the web dashboard backend.

@author Luca D'Aurizio
"""

from models.token import SystemStats

__all__ = ["SystemStats"]
