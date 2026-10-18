"""
Animus HTTP API

FastAPI-based REST API for external access to Animus functionality.

Requires: pip install 'animus[api]'
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from animus.cognitive import CognitiveLayer, ReasoningMode, detect_mode
from animus.config import AnimusConfig
from animus.decision import DecisionFramework
from animus.logging import get_logger
from animus.memory import Conversation, MemoryLayer, MemoryType
from animus.tasks import TaskStatus, TaskTracker
from animus.tools import ToolRegistry

if TYPE_CHECKING:
    from animus.autonomous import AutonomousExecutor
    from animus.entities import EntityMemory
    from animus.integrations.manager import IntegrationManager
    from animus.learning import LearningLayer
    from animus.proactive import ProactiveEngine

logger = get_logger("api")

# Check for FastAPI dependency
try:
    import uvicorn
    from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse
    from fastapi.security import APIKeyHeader

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


# =============================================================================
# Request/Response Models (Pydantic, always available)
# =============================================================================


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., description="User message")
    mode: str = Field(default="auto", description="Reasoning mode: auto, quick, deep, research")
    conversation_id: str | None = Field(default=None, description="Continue existing conversation")


class ChatResponse(BaseModel):
    """Chat response model."""

    response: str
    conversation_id: str
    mode_used: str


class MemoryCreate(BaseModel):
    """Create memory request."""

    content: str
    memory_type: str = "semantic"
    tags: list[str] = []
    source: str = "stated"
    confidence: float = 1.0


class MemoryResponse(BaseModel):
    """Memory response model."""

    id: str
    content: str
    memory_type: str
    tags: list[str]
    source: str
    confidence: float
    created_at: str
    updated_at: str


class MemorySearchResponse(BaseModel):
    """Memory search response."""

    memories: list[MemoryResponse]
    count: int


class TaskCreate(BaseModel):
    """Create task request."""

    description: str
    tags: list[str] = []
    priority: int = 0


class TaskResponse(BaseModel):
    """Task response model."""

    id: str
    description: str
    status: str
    tags: list[str]
    priority: int
    created_at: str


class TaskUpdate(BaseModel):
    """Update task request."""

    status: str | None = None
    description: str | None = None


class ToolExecute(BaseModel):
    """Tool execution request."""

    params: dict = {}


class ToolResponse(BaseModel):
    """Tool response model."""

    name: str
    success: bool
    output: str | None
    error: str | None


class DecisionRequest(BaseModel):
    """Decision analysis request."""

    question: str
    options: list[str] | None = None
    criteria: list[str] | None = None


class StatusResponse(BaseModel):
    """System status response."""

    status: str
    version: str
    memory_count: int
    task_count: int
    model_provider: str
    model_name: str


class BriefResponse(BaseModel):
    """Briefing response."""

    briefing: str
    topic: str | None


class IntegrationResponse(BaseModel):
    """Integration status response."""

    name: str
    display_name: str
    status: str
    auth_type: str
    connected_at: str | None
    error_message: str | None
    capabilities: list[str]


class IntegrationListResponse(BaseModel):
    """List of integrations."""

    integrations: list[IntegrationResponse]
    connected_count: int


class IntegrationConnectRequest(BaseModel):
    """Connect to integration request."""

    credentials: dict = {}


class LearnedItemResponse(BaseModel):
    """Learned item response."""

    id: str
    category: str
    content: str
    confidence: float
    applied: bool
    created_at: str
    updated_at: str


class LearningDashboardResponse(BaseModel):
    """Learning dashboard response."""

    total_learned: int
    pending_approval: int
    events_today: int
    guardrail_violations: int
    by_category: dict[str, int]
    confidence_distribution: dict[str, int]


class GuardrailResponse(BaseModel):
    """Guardrail response."""

    id: str
    rule: str
    description: str
    guardrail_type: str
    immutable: bool
    source: str


class RollbackPointResponse(BaseModel):
    """Rollback point response."""

    id: str
    timestamp: str
    description: str
    item_count: int


# =============================================================================
# Application State
# =============================================================================


@dataclass
class AppState:
    """Shared application state."""

    config: AnimusConfig
    memory: MemoryLayer
    cognitive: CognitiveLayer
    tools: ToolRegistry
    tasks: TaskTracker
    decisions: DecisionFramework
    conversations: dict[str, Conversation]
    integrations: IntegrationManager | None = None  # IntegrationManager (optional)
    learning: LearningLayer | None = None  # LearningLayer (optional)
    entity_memory: EntityMemory | None = None  # EntityMemory (optional)
    proactive: ProactiveEngine | None = None  # ProactiveEngine (optional)
    executor: AutonomousExecutor | None = None  # AutonomousExecutor (optional)


_state: AppState | None = None


# =============================================================================
# API Server Class
# =============================================================================


class APIServer:
    """
    Manages the API server lifecycle.

    Provides a simple interface to start/stop the FastAPI server
    from the CLI without blocking the main thread.
    """

    def __init__(
        self,
        memory: MemoryLayer,
        cognitive: CognitiveLayer,
        tools: ToolRegistry,
        tasks: TaskTracker,
        decisions: DecisionFramework,
        host: str = "127.0.0.1",
        port: int = 8420,
        api_key: str | None = None,
        integrations: IntegrationManager | None = None,
        learning: LearningLayer | None = None,
        entity_memory: EntityMemory | None = None,
        proactive: ProactiveEngine | None = None,
        executor: AutonomousExecutor | None = None,
    ):
        """
        Initialize API server.

        Args:
            memory: MemoryLayer instance
            cognitive: CognitiveLayer instance
            tools: ToolRegistry instance
            tasks: TaskTracker instance
            decisions: DecisionFramework instance
            host: Host to bind to
            port: Port to bind to
            api_key: Optional API key for authentication
            integrations: Optional IntegrationManager instance
            learning: Optional LearningLayer instance
            entity_memory: Optional EntityMemory instance
            proactive: Optional ProactiveEngine instance
            executor: Optional AutonomousExecutor instance
        """
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI not installed. Install with: pip install 'animus[api]'")

        self.memory = memory
        self.cognitive = cognitive
        self.tools = tools
        self.tasks = tasks
        self.decisions = decisions
        self.host = host
        self.port = port
        self.api_key = api_key
        self.integrations = integrations
        self.learning = learning
        self.entity_memory = entity_memory
        self.proactive = proactive
        self.executor = executor

        self._server_thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._is_running = False

    def start(self) -> bool:
        """Start the API server in a background thread."""
        global _state

        if self._is_running:
            logger.warning("Server already running")
            return False

        # Initialize global state
        _state = AppState(
            config=AnimusConfig.load(),
            memory=self.memory,
            cognitive=self.cognitive,
            tools=self.tools,
            tasks=self.tasks,
            decisions=self.decisions,
            conversations={},
            integrations=self.integrations,
            learning=self.learning,
            entity_memory=self.entity_memory,
            proactive=self.proactive,
            executor=self.executor,
        )

        # Update config with API key if provided
        if self.api_key:
            _state.config.api.api_key = self.api_key

        def run_server():
            import asyncio

            # Create app inside thread to avoid issues
            app = create_app()

            config = uvicorn.Config(
                app,
                host=self.host,
                port=self.port,
                log_level="warning",
            )
            self._server = uvicorn.Server(config)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._server.serve())

        self._server_thread = threading.Thread(target=run_server, daemon=True)
        self._server_thread.start()
        self._is_running = True

        logger.info(f"API server started on http://{self.host}:{self.port}")
        return True

    def stop(self) -> bool:
        """Stop the API server."""
        if not self._is_running:
            return False

        if self._server:
            self._server.should_exit = True

        self._is_running = False
        logger.info("API server stopped")
        return True

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._is_running

    @property
    def url(self) -> str:
        """Get server URL."""
        return f"http://{self.host}:{self.port}"


# =============================================================================
# FastAPI App Factory
# =============================================================================


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    This factory function creates the app with all routes registered.
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed. Install with: pip install 'animus[api]'")

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        """Application lifespan management."""
        logger.info("Animus API starting up")
        yield
        logger.info("Animus API shutting down")

    app = FastAPI(
        title="Animus API",
        description="Personal AI exocortex API",
        version="0.4.0",
        lifespan=lifespan,
    )

    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def get_state() -> AppState:
        """Get application state."""
        if _state is None:
            raise HTTPException(status_code=503, detail="Server not initialized")
        return _state

    async def verify_api_key(api_key: str | None = Depends(api_key_header)) -> bool:
        """Verify API key if configured."""
        state = get_state()
        configured_key = state.config.api.api_key

        if configured_key is None:
            return True  # No auth required

        if api_key is None or api_key != configured_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        return True

    # =========================================================================
    # Endpoints
    # =========================================================================

    @app.get("/status", response_model=StatusResponse)
    async def get_status():
        """Get system status."""
        state = get_state()
        memories = state.memory.store.list_all()
        tasks = state.tasks.list(include_completed=True)

        return StatusResponse(
            status="running",
            version="0.4.0",
            memory_count=len(memories),
            task_count=len(tasks),
            model_provider=state.config.model.provider,
            model_name=state.config.model.name,
        )

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest, _auth: bool = Depends(verify_api_key)):
        """Send a chat message and get a response."""
        state = get_state()

        # Get or create conversation
        if request.conversation_id and request.conversation_id in state.conversations:
            conversation = state.conversations[request.conversation_id]
        else:
            conversation = Conversation.new()
            state.conversations[conversation.id] = conversation

        # Determine mode
        if request.mode == "auto":
            mode = detect_mode(request.message)
        else:
            mode = ReasoningMode(request.mode)

        # Get context from memory
        context_memories = state.memory.recall(request.message, limit=3)
        context = "\n".join(m.content for m in context_memories) if context_memories else None

        # Generate response
        conversation.add_message("user", request.message)
        response = state.cognitive.think(request.message, context=context, mode=mode)
        conversation.add_message("assistant", response)

        return ChatResponse(
            response=response,
            conversation_id=conversation.id,
            mode_used=mode.value,
        )

    # Memory endpoints

    @app.post("/memory", response_model=MemoryResponse)
    async def create_memory(request: MemoryCreate, _auth: bool = Depends(verify_api_key)):
        """Create a new memory."""
        state = get_state()

        try:
            mem_type = MemoryType(request.memory_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid memory type: {request.memory_type}"
            )

        memory = state.memory.remember(
            content=request.content,
            memory_type=mem_type,
            tags=request.tags,
            source=request.source,
            confidence=request.confidence,
        )

        return MemoryResponse(
            id=memory.id,
            content=memory.content,
            memory_type=memory.memory_type.value,
            tags=memory.tags,
            source=memory.source,
            confidence=memory.confidence,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
        )

    @app.get("/memory/search", response_model=MemorySearchResponse)
    async def search_memories(
        query: str = Query(..., description="Search query"),
        limit: int = Query(default=10, le=100),
        tags: str | None = Query(default=None, description="Comma-separated tags"),
        _auth: bool = Depends(verify_api_key),
    ):
        """Search memories."""
        state = get_state()

        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        memories = state.memory.recall(query, tags=tag_list, limit=limit)

        return MemorySearchResponse(
            memories=[
                MemoryResponse(
                    id=m.id,
                    content=m.content,
                    memory_type=m.memory_type.value,
                    tags=m.tags,
                    source=m.source,
                    confidence=m.confidence,
                    created_at=m.created_at.isoformat(),
                    updated_at=m.updated_at.isoformat(),
                )
                for m in memories
            ],
            count=len(memories),
        )

    @app.get("/memory/{memory_id}", response_model=MemoryResponse)
    async def get_memory(memory_id: str, _auth: bool = Depends(verify_api_key)):
        """Get a specific memory by ID."""
        state = get_state()
        memory = state.memory.get_memory(memory_id)

        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        return MemoryResponse(
            id=memory.id,
            content=memory.content,
            memory_type=memory.memory_type.value,
            tags=memory.tags,
            source=memory.source,
            confidence=memory.confidence,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
        )

    @app.delete("/memory/{memory_id}")
    async def delete_memory(memory_id: str, _auth: bool = Depends(verify_api_key)):
        """Delete a memory."""
        state = get_state()

        if state.memory.forget(memory_id):
            return {"status": "deleted", "id": memory_id}
        else:
            raise HTTPException(status_code=404, detail="Memory not found")

    # Tool endpoints

    @app.get("/tools")
    async def list_tools(_auth: bool = Depends(verify_api_key)):
        """List available tools."""
        state = get_state()
        tools = state.tools.list_tools()

        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                    "requires_approval": t.requires_approval,
                }
                for t in tools
            ]
        }

    @app.post("/tools/{tool_name}", response_model=ToolResponse)
    async def execute_tool(
        tool_name: str, request: ToolExecute, _auth: bool = Depends(verify_api_key)
    ):
        """Execute a tool."""
        state = get_state()

        tool = state.tools.get(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

        if tool.requires_approval:
            raise HTTPException(
                status_code=403,
                detail=f"Tool '{tool_name}' requires approval (not available via API)",
            )

        result = state.tools.execute(tool_name, request.params)

        return ToolResponse(
            name=result.tool_name,
            success=result.success,
            output=str(result.output) if result.output else None,
            error=result.error,
        )

    # Task endpoints

    @app.get("/tasks")
    async def list_tasks(
        status: str | None = Query(default=None),
        include_completed: bool = Query(default=False),
        _auth: bool = Depends(verify_api_key),
    ):
        """List tasks."""
        state = get_state()

        status_filter = TaskStatus(status) if status else None
        tasks = state.tasks.list(status=status_filter, include_completed=include_completed)

        return {
            "tasks": [
                TaskResponse(
                    id=t.id,
                    description=t.description,
                    status=t.status.value,
                    tags=t.tags,
                    priority=t.priority,
                    created_at=t.created_at.isoformat(),
                )
                for t in tasks
            ]
        }

    @app.post("/tasks", response_model=TaskResponse)
    async def create_task(request: TaskCreate, _auth: bool = Depends(verify_api_key)):
        """Create a new task."""
        state = get_state()

        task = state.tasks.add(
            description=request.description,
            tags=request.tags,
            priority=request.priority,
        )

        return TaskResponse(
            id=task.id,
            description=task.description,
            status=task.status.value,
            tags=task.tags,
            priority=task.priority,
            created_at=task.created_at.isoformat(),
        )

    @app.patch("/tasks/{task_id}", response_model=TaskResponse)
    async def update_task(task_id: str, request: TaskUpdate, _auth: bool = Depends(verify_api_key)):
        """Update a task."""
        state = get_state()

        task = state.tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if request.status:
            try:
                state.tasks.update_status(task_id, TaskStatus(request.status))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")

        task = state.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        return TaskResponse(
            id=task.id,
            description=task.description,
            status=task.status.value,
            tags=task.tags,
            priority=task.priority,
            created_at=task.created_at.isoformat(),
        )

    @app.delete("/tasks/{task_id}")
    async def delete_task(task_id: str, _auth: bool = Depends(verify_api_key)):
        """Delete a task."""
        state = get_state()

        if state.tasks.delete(task_id):
            return {"status": "deleted", "id": task_id}
        else:
            raise HTTPException(status_code=404, detail="Task not found")

    # Decision endpoint

    @app.post("/decide")
    async def analyze_decision(request: DecisionRequest, _auth: bool = Depends(verify_api_key)):
        """Perform decision analysis."""
        state = get_state()

        decision = state.decisions.analyze(
            question=request.question,
            options=request.options,
            criteria=request.criteria,
        )

        return {
            "question": decision.question,
            "options": decision.options,
            "criteria": decision.criteria,
            "analysis": decision.analysis,
            "recommendation": decision.recommendation,
            "reasoning": decision.reasoning,
        }

    # Briefing endpoint

    @app.get("/brief", response_model=BriefResponse)
    async def get_briefing(
        topic: str | None = Query(default=None), _auth: bool = Depends(verify_api_key)
    ):
        """Generate a situation briefing."""
        state = get_state()

        briefing = state.cognitive.brief(state.memory, topic=topic)

        return BriefResponse(briefing=briefing, topic=topic)

    # WebSocket endpoint

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        """WebSocket endpoint for streaming chat."""
        await websocket.accept()
        state = get_state()

        conversation = Conversation.new()
        state.conversations[conversation.id] = conversation

        try:
            while True:
                data = await websocket.receive_json()
                message = data.get("message", "")

                if not message:
                    await websocket.send_json({"error": "No message provided"})
                    continue

                # Get mode
                mode_str = data.get("mode", "auto")
                if mode_str == "auto":
                    mode = detect_mode(message)
                else:
                    mode = ReasoningMode(mode_str)

                # Get context
                context_memories = state.memory.recall(message, limit=3)
                context = (
                    "\n".join(m.content for m in context_memories) if context_memories else None
                )

                # Generate response
                conversation.add_message("user", message)
                response = state.cognitive.think(message, context=context, mode=mode)
                conversation.add_message("assistant", response)

                await websocket.send_json(
                    {
                        "response": response,
                        "conversation_id": conversation.id,
                        "mode_used": mode.value,
                    }
                )

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {conversation.id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await websocket.close(code=1011)

    # Integration endpoints (Phase 4)
    # Note: These endpoints require IntegrationManager to be set on state

    @app.get("/integrations", response_model=IntegrationListResponse)
    async def list_integrations(_auth: bool = Depends(verify_api_key)):
        """List all integrations with their status."""
        state = get_state()

        if not hasattr(state, "integrations") or state.integrations is None:
            return IntegrationListResponse(integrations=[], connected_count=0)

        all_integrations = state.integrations.list_all()
        connected_count = len([i for i in all_integrations if i.status.value == "connected"])

        return IntegrationListResponse(
            integrations=[
                IntegrationResponse(
                    name=i.name,
                    display_name=i.display_name,
                    status=i.status.value,
                    auth_type=i.auth_type.value,
                    connected_at=i.connected_at.isoformat() if i.connected_at else None,
                    error_message=i.error_message,
                    capabilities=i.capabilities,
                )
                for i in all_integrations
            ],
            connected_count=connected_count,
        )

    @app.post("/integrations/{service}/connect", response_model=IntegrationResponse)
    async def connect_integration(
        service: str,
        request: IntegrationConnectRequest,
        _auth: bool = Depends(verify_api_key),
    ):
        """Connect to an integration."""
        state = get_state()

        if not hasattr(state, "integrations") or state.integrations is None:
            raise HTTPException(
                status_code=503,
                detail="Integration manager not available",
            )

        integration = state.integrations.get(service)
        if not integration:
            raise HTTPException(
                status_code=404,
                detail=f"Integration not found: {service}",
            )

        success = await state.integrations.connect(service, request.credentials)

        if not success:
            info = integration.get_info()
            raise HTTPException(
                status_code=400,
                detail=f"Failed to connect: {info.error_message}",
            )

        # Register tools after connection
        for tool in integration.get_tools():
            state.tools.register(tool)

        info = integration.get_info()
        return IntegrationResponse(
            name=info.name,
            display_name=info.display_name,
            status=info.status.value,
            auth_type=info.auth_type.value,
            connected_at=info.connected_at.isoformat() if info.connected_at else None,
            error_message=info.error_message,
            capabilities=info.capabilities,
        )

    @app.delete("/integrations/{service}")
    async def disconnect_integration(service: str, _auth: bool = Depends(verify_api_key)):
        """Disconnect from an integration."""
        state = get_state()

        if not hasattr(state, "integrations") or state.integrations is None:
            raise HTTPException(
                status_code=503,
                detail="Integration manager not available",
            )

        integration = state.integrations.get(service)
        if not integration:
            raise HTTPException(
                status_code=404,
                detail=f"Integration not found: {service}",
            )

        success = await state.integrations.disconnect(service)

        if success:
            return {"status": "disconnected", "service": service}
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to disconnect",
            )

    # =========================================================================
    # Learning Endpoints (Phase 5)
    # =========================================================================

    @app.get("/learning/status", response_model=LearningDashboardResponse)
    async def learning_status(_auth: bool = Depends(verify_api_key)):
        """Get learning system dashboard."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        dashboard = state.learning.get_dashboard_data()
        return LearningDashboardResponse(
            total_learned=dashboard.total_learned,
            pending_approval=dashboard.pending_approval,
            events_today=dashboard.events_today,
            guardrail_violations=dashboard.guardrail_violations,
            by_category=dashboard.by_category,
            confidence_distribution=dashboard.confidence_distribution,
        )

    @app.get("/learning/items")
    async def list_learned_items(
        status: str = Query(default="all"),  # active, pending, all
        _auth: bool = Depends(verify_api_key),
    ):
        """List learned items."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        if status == "active":
            items = state.learning.get_active_learnings()
        elif status == "pending":
            items = state.learning.get_pending_learnings()
        else:
            items = state.learning.get_all_learnings()

        return {
            "items": [
                LearnedItemResponse(
                    id=item.id,
                    category=item.category.value,
                    content=item.content,
                    confidence=item.confidence,
                    applied=item.applied,
                    created_at=item.created_at.isoformat(),
                    updated_at=item.updated_at.isoformat(),
                )
                for item in items
            ],
            "count": len(items),
        }

    @app.post("/learning/scan")
    async def trigger_learning_scan(_auth: bool = Depends(verify_api_key)):
        """Trigger pattern detection scan."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        patterns = state.learning.scan_and_learn()
        return {"patterns_detected": len(patterns)}

    @app.post("/learning/{item_id}/approve")
    async def approve_learning(item_id: str, _auth: bool = Depends(verify_api_key)):
        """Approve a pending learning."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        if state.learning.approve_learning(item_id):
            return {"status": "approved", "id": item_id}
        raise HTTPException(status_code=404, detail="Learning not found or already applied")

    @app.post("/learning/{item_id}/reject")
    async def reject_learning(
        item_id: str,
        reason: str = Query(default=""),
        _auth: bool = Depends(verify_api_key),
    ):
        """Reject a pending learning."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        if state.learning.reject_learning(item_id, reason):
            return {"status": "rejected", "id": item_id}
        raise HTTPException(status_code=404, detail="Learning not found")

    @app.delete("/learning/{item_id}")
    async def unlearn(item_id: str, _auth: bool = Depends(verify_api_key)):
        """Unlearn a specific item."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        if state.learning.unlearn(item_id):
            return {"status": "unlearned", "id": item_id}
        raise HTTPException(status_code=404, detail="Learning not found")

    @app.get("/learning/history")
    async def learning_history(
        limit: int = Query(default=50, le=500),
        event_type: str | None = Query(default=None),
        _auth: bool = Depends(verify_api_key),
    ):
        """Get learning event history."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        events = state.learning.transparency.get_history(limit=limit, event_type=event_type)
        return {"events": [e.to_dict() for e in events]}

    @app.get("/guardrails")
    async def list_guardrails(_auth: bool = Depends(verify_api_key)):
        """List all guardrails."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        guardrails = state.learning.guardrails.get_all_guardrails()
        return {
            "guardrails": [
                GuardrailResponse(
                    id=g.id,
                    rule=g.rule,
                    description=g.description,
                    guardrail_type=g.guardrail_type.value,
                    immutable=g.immutable,
                    source=g.source,
                )
                for g in guardrails
            ]
        }

    @app.post("/guardrails")
    async def add_guardrail(
        rule: str = Query(...),
        description: str = Query(default=""),
        _auth: bool = Depends(verify_api_key),
    ):
        """Add a user-defined guardrail."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        guardrail = state.learning.add_user_guardrail(rule, description or f"User-defined: {rule}")
        return {"status": "created", "id": guardrail.id}

    @app.get("/learning/rollback-points")
    async def list_rollback_points(_auth: bool = Depends(verify_api_key)):
        """List available rollback points."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        points = state.learning.rollback.get_rollback_points()
        return {
            "rollback_points": [
                RollbackPointResponse(
                    id=p.id,
                    timestamp=p.timestamp.isoformat(),
                    description=p.description,
                    item_count=len(p.learned_item_ids),
                )
                for p in points
            ]
        }

    @app.post("/learning/rollback/{point_id}")
    async def rollback_to_point(point_id: str, _auth: bool = Depends(verify_api_key)):
        """Rollback to a specific point."""
        state = get_state()
        if not hasattr(state, "learning") or state.learning is None:
            raise HTTPException(
                status_code=503,
                detail="Learning system not available",
            )

        success, unlearned = state.learning.rollback_to(point_id)
        if success:
            return {"status": "rolled_back", "unlearned_count": len(unlearned)}
        raise HTTPException(status_code=404, detail="Rollback point not found")

    # =====================================================================
    # Memory Export & Consolidation
    # =====================================================================

    @app.get("/memory/export/csv")
    async def export_memories_csv(_auth: bool = Depends(verify_api_key)):
        """Export all memories in CSV format."""
        state = get_state()
        csv_data = state.memory.export_memories_csv()
        from starlette.responses import Response

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=memories.csv"},
        )

    @app.post("/memory/consolidate")
    async def consolidate_memories(
        max_age_days: int = 90,
        min_group_size: int = 3,
        _auth: bool = Depends(verify_api_key),
    ):
        """Consolidate old memories into summaries."""
        state = get_state()
        count = state.memory.consolidate(
            max_age_days=max_age_days,
            min_group_size=min_group_size,
        )
        return {"consolidated": count}

    # =====================================================================
    # Register Translation
    # =====================================================================

    @app.get("/register")
    async def get_register(_auth: bool = Depends(verify_api_key)):
        """Get current communication register."""
        state = get_state()
        return state.cognitive.register_translator.get_register_context()

    @app.post("/register/{register_name}")
    async def set_register(register_name: str, _auth: bool = Depends(verify_api_key)):
        """Override communication register (formal, casual, technical, neutral)."""
        from animus.register import Register

        state = get_state()
        try:
            reg = Register(register_name)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown register: {register_name}. Use: formal, casual, technical, neutral",
            )

        if reg == Register.NEUTRAL:
            state.cognitive.register_translator.set_override(None)
        else:
            state.cognitive.register_translator.set_override(reg)
        return state.cognitive.register_translator.get_register_context()

    # =====================================================================
    # Proactive Intelligence
    # =====================================================================

    @app.get("/nudges")
    async def get_nudges(_auth: bool = Depends(verify_api_key)):
        """Get active proactive nudges."""
        state = get_state()
        if not hasattr(state, "proactive") or state.proactive is None:
            return {"nudges": [], "count": 0}
        nudges = state.proactive.get_active_nudges()
        return {
            "nudges": [n.to_dict() for n in nudges],
            "count": len(nudges),
        }

    @app.post("/nudges/briefing")
    async def generate_briefing(_auth: bool = Depends(verify_api_key)):
        """Generate a morning briefing."""
        state = get_state()
        if not hasattr(state, "proactive") or state.proactive is None:
            raise HTTPException(status_code=503, detail="Proactive engine not available")
        nudge = state.proactive.generate_morning_brief()
        return nudge.to_dict()

    @app.post("/nudges/meeting-prep")
    async def meeting_prep(topic: str, _auth: bool = Depends(verify_api_key)):
        """Prepare context for a meeting."""
        state = get_state()
        if not hasattr(state, "proactive") or state.proactive is None:
            raise HTTPException(status_code=503, detail="Proactive engine not available")
        nudge = state.proactive.prepare_meeting_context(topic)
        return nudge.to_dict()

    @app.post("/nudges/{nudge_id}/dismiss")
    async def dismiss_nudge(nudge_id: str, _auth: bool = Depends(verify_api_key)):
        """Dismiss a nudge."""
        state = get_state()
        if not hasattr(state, "proactive") or state.proactive is None:
            raise HTTPException(status_code=503, detail="Proactive engine not available")
        success = state.proactive.dismiss_nudge(nudge_id)
        if not success:
            raise HTTPException(status_code=404, detail="Nudge not found")
        return {"status": "dismissed"}

    @app.get("/proactive/stats")
    async def proactive_stats(_auth: bool = Depends(verify_api_key)):
        """Get proactive engine statistics."""
        state = get_state()
        if not hasattr(state, "proactive") or state.proactive is None:
            return {"background_running": False, "active_nudges": 0}
        return state.proactive.get_statistics()

    # =====================================================================
    # Entity Memory
    # =====================================================================

    @app.get("/entities")
    async def list_entities(
        entity_type: str | None = None,
        limit: int = 50,
        _auth: bool = Depends(verify_api_key),
    ):
        """List tracked entities."""
        state = get_state()
        if not hasattr(state, "entity_memory") or state.entity_memory is None:
            return {"entities": [], "count": 0}

        from animus.entities import EntityType

        etype = EntityType(entity_type) if entity_type else None
        entities = state.entity_memory.list_entities(entity_type=etype, limit=limit)
        return {
            "entities": [e.to_dict() for e in entities],
            "count": len(entities),
        }

    @app.post("/entities")
    async def create_entity(
        name: str,
        entity_type: str,
        aliases: str | None = None,
        notes: str = "",
        _auth: bool = Depends(verify_api_key),
    ):
        """Add a new entity."""
        state = get_state()
        if not hasattr(state, "entity_memory") or state.entity_memory is None:
            raise HTTPException(status_code=503, detail="Entity memory not available")

        from animus.entities import EntityType

        try:
            etype = EntityType(entity_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown entity type: {entity_type}")

        alias_list = [a.strip() for a in aliases.split(",")] if aliases else []
        entity = state.entity_memory.add_entity(
            name=name, entity_type=etype, aliases=alias_list, notes=notes
        )
        return entity.to_dict()

    @app.get("/entities/search")
    async def search_entities(
        query: str,
        entity_type: str | None = None,
        _auth: bool = Depends(verify_api_key),
    ):
        """Search entities by name, alias, or content."""
        state = get_state()
        if not hasattr(state, "entity_memory") or state.entity_memory is None:
            return {"entities": [], "count": 0}

        from animus.entities import EntityType

        etype = EntityType(entity_type) if entity_type else None
        results = state.entity_memory.search_entities(query, entity_type=etype)
        return {
            "entities": [e.to_dict() for e in results],
            "count": len(results),
        }

    @app.get("/entities/{entity_id}")
    async def get_entity(entity_id: str, _auth: bool = Depends(verify_api_key)):
        """Get entity details with context."""
        state = get_state()
        if not hasattr(state, "entity_memory") or state.entity_memory is None:
            raise HTTPException(status_code=503, detail="Entity memory not available")

        entity = state.entity_memory.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        context = state.entity_memory.generate_entity_context(entity_id)
        data = entity.to_dict()
        data["context"] = context
        data["relationships"] = [
            r.to_dict() for r in state.entity_memory.get_relationships_for(entity_id)
        ]
        return data

    @app.delete("/entities/{entity_id}")
    async def delete_entity(entity_id: str, _auth: bool = Depends(verify_api_key)):
        """Delete an entity."""
        state = get_state()
        if not hasattr(state, "entity_memory") or state.entity_memory is None:
            raise HTTPException(status_code=503, detail="Entity memory not available")

        success = state.entity_memory.delete_entity(entity_id)
        if not success:
            raise HTTPException(status_code=404, detail="Entity not found")
        return {"status": "deleted"}

    @app.get("/entities/{entity_id}/timeline")
    async def entity_timeline(
        entity_id: str,
        limit: int = 20,
        _auth: bool = Depends(verify_api_key),
    ):
        """Get interaction timeline for an entity."""
        state = get_state()
        if not hasattr(state, "entity_memory") or state.entity_memory is None:
            raise HTTPException(status_code=503, detail="Entity memory not available")

        timeline = state.entity_memory.get_interaction_timeline(entity_id, limit=limit)
        return {
            "entity_id": entity_id,
            "interactions": [i.to_dict() for i in timeline],
        }

    @app.get("/entities/stats")
    async def entity_stats(_auth: bool = Depends(verify_api_key)):
        """Get entity memory statistics."""
        state = get_state()
        if not hasattr(state, "entity_memory") or state.entity_memory is None:
            return {"total_entities": 0}
        return state.entity_memory.get_statistics()

    # =====================================================================
    # Dashboard
    # =====================================================================

    # =====================================================================
    # Autonomous Action Endpoints
    # =====================================================================

    @app.get("/autonomous/actions")
    async def list_autonomous_actions(limit: int = 20, _auth: bool = Depends(verify_api_key)):
        """List recent autonomous actions."""
        state = get_state()
        ex = getattr(state, "executor", None)
        if not ex:
            return {"actions": [], "enabled": False}
        return {
            "actions": [a.to_dict() for a in ex.get_recent_actions(limit)],
            "enabled": True,
        }

    @app.get("/autonomous/pending")
    async def list_pending_actions(_auth: bool = Depends(verify_api_key)):
        """List actions awaiting user approval."""
        state = get_state()
        ex = getattr(state, "executor", None)
        if not ex:
            return {"actions": []}
        return {"actions": [a.to_dict() for a in ex.get_pending_actions()]}

    @app.post("/autonomous/actions/{action_id}/approve")
    async def approve_action(action_id: str, _auth: bool = Depends(verify_api_key)):
        """Approve a pending autonomous action."""
        state = get_state()
        ex = getattr(state, "executor", None)
        if not ex:
            return JSONResponse(
                status_code=404, content={"detail": "Autonomous executor not enabled"}
            )
        action = ex.approve_action(action_id)
        if not action:
            return JSONResponse(status_code=404, content={"detail": "Action not found"})
        return action.to_dict()

    @app.post("/autonomous/actions/{action_id}/deny")
    async def deny_action(action_id: str, _auth: bool = Depends(verify_api_key)):
        """Deny a pending autonomous action."""
        state = get_state()
        ex = getattr(state, "executor", None)
        if not ex:
            return JSONResponse(
                status_code=404, content={"detail": "Autonomous executor not enabled"}
            )
        action = ex.deny_action(action_id)
        if not action:
            return JSONResponse(status_code=404, content={"detail": "Action not found"})
        return action.to_dict()

    @app.get("/autonomous/stats")
    async def autonomous_stats(_auth: bool = Depends(verify_api_key)):
        """Get autonomous executor statistics."""
        state = get_state()
        ex = getattr(state, "executor", None)
        if not ex:
            return {"enabled": False}
        stats = ex.get_statistics()
        stats["enabled"] = True
        return stats

    try:
        from animus.dashboard import add_dashboard_routes

        add_dashboard_routes(app, get_state, verify_api_key)
    except ImportError:
        pass  # Optional dependency: dashboard module not installed

    return app
