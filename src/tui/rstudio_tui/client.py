"""
RStudio Session RPC Client

Handles JSON-RPC communication with the rsession backend.
Based on the protocol defined in src/cpp/core/include/core/json/JsonRpc.hpp
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class RpcErrorCode(IntEnum):
    """RPC error codes from JsonRpc.hpp"""

    # JSON-RPC 2.0 standard errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # RStudio-specific errors (lines 41-80 in JsonRpc.hpp)
    NO_ERROR = 0
    CONNECTION_ERROR = 1
    UNAVAILABLE = 2
    UNAUTHORIZED = 3
    INVALID_CLIENT_ID = 4
    PROTOCOL_ERROR = 5
    INVALID_SESSION = 6
    MAX_SESSIONS_REACHED = 7
    MAX_USERS_REACHED = 8
    LAUNCH_PARAMETERS_MISSING = 9
    LIMIT_EXCEEDED = 10
    EXECUTION_ERROR = 100
    TRANSMISSION_ERROR = 200


@dataclass
class RpcResponse:
    """Response from an RPC call"""
    result: Any = None
    error: Optional[Dict[str, Any]] = None

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def error_message(self) -> str:
        if self.error:
            return self.error.get("message", "Unknown error")
        return ""

    @property
    def error_code(self) -> int:
        if self.error:
            return self.error.get("code", RpcErrorCode.INTERNAL_ERROR)
        return RpcErrorCode.NO_ERROR


@dataclass
class ClientEvent:
    """Event sent from rsession to client"""
    type: int
    data: Any
    id: int = 0


class RSessionClient:
    """
    Client for communicating with rsession via JSON-RPC.

    The rsession backend uses a JSON-RPC protocol over HTTP. This client
    implements the same protocol used by the GWT and Electron frontends.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8787,
        secure: bool = False,
        shared_secret: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.secure = secure
        self.shared_secret = shared_secret

        self._client_id: str = str(uuid.uuid4())
        self._client_version: str = "2024.09.0"
        self._http_client: Optional[httpx.AsyncClient] = None
        self._event_handlers: Dict[int, List[Callable[[ClientEvent], None]]] = {}
        self._last_event_id: int = 0
        self._polling: bool = False
        self._poll_task: Optional[asyncio.Task] = None

    @property
    def base_url(self) -> str:
        protocol = "https" if self.secure else "http"
        return f"{protocol}://{self.host}:{self.port}"

    async def connect(self) -> bool:
        """
        Establish connection to rsession.

        Returns True if connection is successful.
        """
        self._http_client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers=self._build_headers(),
        )

        # Initialize the client with rsession
        try:
            response = await self.call("client_init", {
                "baseURL": self.base_url,
                "workbenchMode": "tui",
            })
            if response.success:
                logger.info("Connected to rsession successfully")
                return True
            else:
                logger.error(f"Failed to initialize client: {response.error_message}")
                return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Close the connection to rsession."""
        self.stop_event_polling()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers for requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.shared_secret:
            headers["X-Shared-Secret"] = self.shared_secret
        return headers

    async def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        kwparams: Optional[Dict[str, Any]] = None,
    ) -> RpcResponse:
        """
        Make an RPC call to rsession.

        Args:
            method: The RPC method name
            params: Positional parameters (as a list or dict)
            kwparams: Keyword parameters

        Returns:
            RpcResponse with result or error
        """
        if not self._http_client:
            return RpcResponse(error={"code": RpcErrorCode.CONNECTION_ERROR, "message": "Not connected"})

        # Build the request payload
        payload = {
            "method": method,
            "params": params if params is not None else [],
            "clientId": self._client_id,
            "clientVersion": self._client_version,
        }
        if kwparams:
            payload["kwparams"] = kwparams

        try:
            response = await self._http_client.post(
                f"/rpc/{method}",
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                return RpcResponse(
                    result=data.get("result"),
                    error=data.get("error"),
                )
            else:
                return RpcResponse(error={
                    "code": RpcErrorCode.CONNECTION_ERROR,
                    "message": f"HTTP {response.status_code}: {response.text}",
                })
        except httpx.TimeoutException:
            return RpcResponse(error={
                "code": RpcErrorCode.CONNECTION_ERROR,
                "message": "Request timed out",
            })
        except Exception as e:
            return RpcResponse(error={
                "code": RpcErrorCode.CONNECTION_ERROR,
                "message": str(e),
            })

    # -------------------------------------------------------------------------
    # Console Operations
    # -------------------------------------------------------------------------

    async def console_input(self, code: str, console_id: str = "") -> RpcResponse:
        """Send input to the R console."""
        return await self.call("console_input", {
            "code": code,
            "console": console_id,
        })

    async def interrupt(self) -> RpcResponse:
        """Interrupt the current R computation."""
        return await self.call("interrupt")

    async def get_console_history(self, max_items: int = 500) -> RpcResponse:
        """Get console command history."""
        return await self.call("get_history", {"maxItems": max_items})

    async def get_console_history_archive(
        self,
        start_index: int = 0,
        max_items: int = 100,
    ) -> RpcResponse:
        """Get archived console history."""
        return await self.call("get_history_archive", {
            "startIndex": start_index,
            "maxItems": max_items,
        })

    # -------------------------------------------------------------------------
    # Environment Operations
    # -------------------------------------------------------------------------

    async def list_environment(self) -> RpcResponse:
        """Get list of objects in the current environment."""
        return await self.call("list_environment")

    async def get_environment_names(self) -> RpcResponse:
        """Get names of available environments."""
        return await self.call("get_environment_names")

    async def set_environment(self, name: str) -> RpcResponse:
        """Set the active environment for viewing."""
        return await self.call("set_environment", {"name": name})

    async def get_object_contents(self, name: str) -> RpcResponse:
        """Get detailed contents of an object."""
        return await self.call("get_object_contents", {"name": name})

    async def remove_objects(self, names: List[str]) -> RpcResponse:
        """Remove objects from the environment."""
        return await self.call("remove_objects", {"names": names})

    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------

    async def list_files(self, path: str) -> RpcResponse:
        """List files in a directory."""
        return await self.call("list_files", {"path": path})

    async def create_folder(self, path: str) -> RpcResponse:
        """Create a new folder."""
        return await self.call("create_folder", {"path": path})

    async def delete_files(self, paths: List[str]) -> RpcResponse:
        """Delete files or folders."""
        return await self.call("delete_files", {"paths": paths})

    async def copy_file(self, source: str, target: str) -> RpcResponse:
        """Copy a file."""
        return await self.call("copy_file", {"sourceFile": source, "targetFile": target})

    async def move_files(self, sources: List[str], target_dir: str) -> RpcResponse:
        """Move files to a target directory."""
        return await self.call("move_files", {"files": sources, "targetDirectory": target_dir})

    async def get_file_contents(self, path: str, encoding: str = "UTF-8") -> RpcResponse:
        """Get contents of a file."""
        return await self.call("get_file_contents", {"path": path, "encoding": encoding})

    async def stat_file(self, path: str) -> RpcResponse:
        """Get file/directory information."""
        return await self.call("stat", {"path": path})

    # -------------------------------------------------------------------------
    # Source/Document Operations
    # -------------------------------------------------------------------------

    async def open_document(self, path: str) -> RpcResponse:
        """Open a document for editing."""
        return await self.call("open_document", {"path": path})

    async def save_document(
        self,
        doc_id: str,
        path: str,
        contents: str,
        encoding: str = "UTF-8",
    ) -> RpcResponse:
        """Save a document."""
        return await self.call("save_document", {
            "id": doc_id,
            "path": path,
            "contents": contents,
            "encoding": encoding,
        })

    async def save_document_diff(
        self,
        doc_id: str,
        path: str,
        contents: str,
        encoding: str = "UTF-8",
    ) -> RpcResponse:
        """Save a document using diff."""
        return await self.call("save_document_diff", {
            "id": doc_id,
            "path": path,
            "contents": contents,
            "encoding": encoding,
        })

    async def close_document(self, doc_id: str) -> RpcResponse:
        """Close a document."""
        return await self.call("close_document", {"id": doc_id})

    async def get_source_document(self, doc_id: str) -> RpcResponse:
        """Get a source document by ID."""
        return await self.call("get_source_document", {"id": doc_id})

    async def new_document(
        self,
        doc_type: str = "r_source",
        contents: str = "",
        encoding: str = "UTF-8",
    ) -> RpcResponse:
        """Create a new document."""
        return await self.call("new_document", {
            "type": doc_type,
            "contents": contents,
            "encoding": encoding,
        })

    # -------------------------------------------------------------------------
    # Help Operations
    # -------------------------------------------------------------------------

    async def search_help(self, query: str) -> RpcResponse:
        """Search the help system."""
        return await self.call("search_help", {"query": query})

    async def get_help(self, topic: str, package: Optional[str] = None) -> RpcResponse:
        """Get help for a topic."""
        params = {"topic": topic}
        if package:
            params["package"] = package
        return await self.call("get_help", params)

    async def show_help_topic(
        self,
        what: str,
        from_package: str = "",
        help_type: str = "",
    ) -> RpcResponse:
        """Show a help topic."""
        return await self.call("show_help_topic", {
            "what": what,
            "from": from_package,
            "type": help_type,
        })

    # -------------------------------------------------------------------------
    # Package Operations
    # -------------------------------------------------------------------------

    async def get_package_state(self) -> RpcResponse:
        """Get current package state."""
        return await self.call("get_package_state")

    async def available_packages(self) -> RpcResponse:
        """Get list of available packages."""
        return await self.call("available_packages")

    async def install_packages(self, packages: List[str]) -> RpcResponse:
        """Install packages."""
        return await self.call("install_packages", {"packages": packages})

    async def remove_packages(self, packages: List[str]) -> RpcResponse:
        """Remove packages."""
        return await self.call("remove_packages", {"packages": packages})

    async def load_package(self, package: str) -> RpcResponse:
        """Load a package (library)."""
        return await self.call("load_package", {"package": package})

    async def unload_package(self, package: str) -> RpcResponse:
        """Unload a package."""
        return await self.call("unload_package", {"package": package})

    # -------------------------------------------------------------------------
    # Working Directory Operations
    # -------------------------------------------------------------------------

    async def get_working_directory(self) -> RpcResponse:
        """Get current working directory."""
        return await self.call("get_working_directory")

    async def set_working_directory(self, path: str) -> RpcResponse:
        """Set working directory."""
        return await self.call("set_working_directory", {"path": path})

    # -------------------------------------------------------------------------
    # Project Operations
    # -------------------------------------------------------------------------

    async def get_active_project_context(self) -> RpcResponse:
        """Get active project context."""
        return await self.call("get_active_project_context")

    async def open_project(self, path: str) -> RpcResponse:
        """Open a project."""
        return await self.call("open_project", {"path": path})

    async def close_project(self) -> RpcResponse:
        """Close the current project."""
        return await self.call("close_project")

    # -------------------------------------------------------------------------
    # Session Operations
    # -------------------------------------------------------------------------

    async def quit_session(self, save_workspace: bool = False) -> RpcResponse:
        """Quit the R session."""
        return await self.call("quit_session", {"saveWorkspace": save_workspace})

    async def suspend_session(self, save: bool = True) -> RpcResponse:
        """Suspend the R session."""
        return await self.call("suspend_session", {"save": save})

    async def get_session_info(self) -> RpcResponse:
        """Get session information."""
        return await self.call("get_session_info")

    # -------------------------------------------------------------------------
    # Completion Operations
    # -------------------------------------------------------------------------

    async def get_completions(
        self,
        line: str,
        cursor_pos: int,
        context_id: str = "",
    ) -> RpcResponse:
        """Get code completions."""
        return await self.call("get_completions", {
            "line": line,
            "cursorPos": cursor_pos,
            "contextId": context_id,
        })

    # -------------------------------------------------------------------------
    # Terminal Operations
    # -------------------------------------------------------------------------

    async def create_terminal(self, caption: str = "") -> RpcResponse:
        """Create a new terminal."""
        return await self.call("create_terminal", {"caption": caption})

    async def send_terminal_input(self, terminal_id: str, input_text: str) -> RpcResponse:
        """Send input to a terminal."""
        return await self.call("send_terminal_input", {
            "id": terminal_id,
            "input": input_text,
        })

    async def close_terminal(self, terminal_id: str) -> RpcResponse:
        """Close a terminal."""
        return await self.call("close_terminal", {"id": terminal_id})

    # -------------------------------------------------------------------------
    # Event Handling
    # -------------------------------------------------------------------------

    def on_event(self, event_type: int, handler: Callable[[ClientEvent], None]) -> None:
        """Register a handler for a specific event type."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def off_event(self, event_type: int, handler: Callable[[ClientEvent], None]) -> None:
        """Remove an event handler."""
        if event_type in self._event_handlers:
            self._event_handlers[event_type].remove(handler)

    def _dispatch_event(self, event: ClientEvent) -> None:
        """Dispatch an event to all registered handlers."""
        # Dispatch to specific handlers
        if event.type in self._event_handlers:
            for handler in self._event_handlers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}")

        # Dispatch to wildcard handlers (type -1)
        if -1 in self._event_handlers:
            for handler in self._event_handlers[-1]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in wildcard event handler: {e}")

    async def poll_events(self) -> List[ClientEvent]:
        """Poll for new events from rsession."""
        response = await self.call("get_events", {
            "lastEventId": self._last_event_id,
        })

        events = []
        if response.success and response.result:
            for event_data in response.result:
                event = ClientEvent(
                    type=event_data.get("type", 0),
                    data=event_data.get("data"),
                    id=event_data.get("id", 0),
                )
                events.append(event)
                if event.id > self._last_event_id:
                    self._last_event_id = event.id
                self._dispatch_event(event)

        return events

    def start_event_polling(self, interval: float = 0.5) -> None:
        """Start polling for events in the background."""
        if self._polling:
            return

        self._polling = True

        async def poll_loop():
            while self._polling:
                try:
                    await self.poll_events()
                except Exception as e:
                    logger.error(f"Error polling events: {e}")
                await asyncio.sleep(interval)

        self._poll_task = asyncio.create_task(poll_loop())

    def stop_event_polling(self) -> None:
        """Stop polling for events."""
        self._polling = False
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None


# Client event type constants (from SessionClientEvent.hpp)
class EventType(IntEnum):
    """Event types sent from rsession to client."""

    BUSY = 0
    CONSOLE_PROMPT = 1
    CONSOLE_WRITE_OUTPUT = 2
    CONSOLE_WRITE_ERROR = 3
    SHOW_ERROR_MESSAGE = 4
    SHOW_HELP = 5
    BROWSE_URL = 6
    WORKSPACE_REFRESH = 7
    WORKSPACE_ASSIGN = 8
    WORKSPACE_REMOVE = 9
    SHOW_EDITOR = 10
    FILE_CHANGED = 11
    WORKING_DIR_CHANGED = 12
    PLOTS_STATE_CHANGED = 13
    VIEW_DATA = 14
    PACKAGE_STATE_CHANGED = 15
    INSTALLED_PACKAGES_CHANGED = 16
    LOCATOR = 17
    CONSOLE_RESET_HISTORY = 18
    SESSION_SERIALIZATION = 19
    HISTORY_ENTRIES_ADDED = 20
    QUIT_SESSION = 21
    SUICIDE = 22
    FILE_EDIT = 23
    SHOW_CONTENT = 24
    SHOW_DATA = 25
    ABORT_EDITING = 26
    SHOW_PRESENTATION_PANE = 27
    ENVIRONMENT_REFRESH = 28
    CONTEXT_DEPTH_CHANGED = 29
    HANDLE_UNSAVED_CHANGES = 30
    CONSOLE_WRITE_INPUT = 35
    ENVIRONMENT_ASSIGNED = 40
    ENVIRONMENT_REMOVED = 41
    BROWSER_LINE_CHANGED = 42
    PACKAGE_LOADED = 43
    PACKAGE_UNLOADED = 44
    OBJECT_EXPLORER_EVENT = 73
    EXECUTE_APP_COMMAND = 88
    MEMORY_USAGE_CHANGED = 93
    JOB_UPDATED = 94
    JOB_REFRESH = 95
    JOB_OUTPUT = 96
    TERMINAL_SUBPROCS = 100
