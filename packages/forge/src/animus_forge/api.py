"""FastAPI backend for AI Workflow Orchestrator."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from animus_forge import api_state as state
from animus_forge.api_errors import (
    APIException,
    RateLimitErrorResponse,
    animus_forge_exception_handler,
    api_exception_handler,
)
from animus_forge.config import configure_logging, get_settings
from animus_forge.errors import AnimusForgeError
from animus_forge.security import (
    AuditLogMiddleware,
    BruteForceConfig,
    BruteForceMiddleware,
    RequestLimitConfig,
    RequestSizeLimitMiddleware,
    get_brute_force_protection,
)
from animus_forge.state import get_database, run_migrations
from animus_forge.tracing.middleware import TracingMiddleware
from animus_forge.utils.circuit_breaker import reset_all_circuits

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


def _handle_shutdown_signal(signum, frame) -> None:
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    state._app_state["shutting_down"] = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage component lifecycles with graceful shutdown."""
    # Reset application state at startup
    state._app_state["ready"] = False
    state._app_state["shutting_down"] = False
    state._app_state["active_requests"] = 0
    state._app_state["start_time"] = datetime.now()

    # Configure logging
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        format=settings.log_format,
        sanitize_logs=settings.sanitize_logs,
    )

    # Register signal handlers for graceful shutdown (only in main thread)
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _handle_shutdown_signal)
        signal.signal(signal.SIGINT, _handle_shutdown_signal)

    # Get shared database backend
    backend = get_database()
    state._app_state["backend"] = backend  # Store for supervisor factory

    # Run migrations
    logger.info("Running database migrations...")
    try:
        applied = run_migrations(backend)
        if applied:
            logger.info(f"Applied migrations: {', '.join(applied)}")
        else:
            logger.info("Database schema is up to date")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

    # Initialize managers with shared backend
    from animus_kernel.executor import WorkflowVersionManager

    from animus_forge.budget import PersistentBudgetManager
    from animus_forge.executions import ExecutionManager
    from animus_forge.jobs import JobManager
    from animus_forge.mcp import MCPConnectorManager
    from animus_forge.scheduler import ScheduleManager
    from animus_forge.settings import SettingsManager
    from animus_forge.webhooks import WebhookManager
    from animus_forge.webhooks.webhook_delivery import WebhookDeliveryManager
    from animus_forge.websocket import Broadcaster, ConnectionManager

    state.execution_manager = ExecutionManager(backend=backend)
    state.schedule_manager = ScheduleManager(backend=backend)
    state.webhook_manager = WebhookManager(backend=backend)
    state.delivery_manager = WebhookDeliveryManager(backend=backend)
    state.job_manager = JobManager(backend=backend, execution_manager=state.execution_manager)
    state.version_manager = WorkflowVersionManager(backend=backend)
    state.mcp_manager = MCPConnectorManager(backend=backend)
    state.settings_manager = SettingsManager(backend=backend)
    state.budget_manager = PersistentBudgetManager(backend=backend)

    from animus_forge.db import TaskStore

    state.task_store = TaskStore(backend=backend)

    # Initialize AreteGuard
    try:
        from animus_forge.security.arete_guard import AreteGuard

        state.arete_guard = AreteGuard(mode="warn")
        logger.info("AreteGuard initialized")
    except Exception as e:
        logger.warning("AreteGuard initialization skipped: %s", e)
        state.arete_guard = None

    # Initialize Research Citizen commissioner
    try:
        from animus_forge.citizens import CitizenCommissioner, ResearchCitizen
        from animus_forge.citizens.store import MissionStore
        from animus_forge.evaluation.base import AgentEvaluator
        from animus_forge.evaluation.loader import SuiteLoader
        from animus_forge.evaluation.runner import EvalRunner
        from animus_forge.evaluation.store import get_eval_store
        from animus_forge.intelligence.cross_workflow_memory import CrossWorkflowMemory
        from animus_forge.intelligence.evidence_bridge import EvidenceBridge
        from animus_forge.intelligence.outcome_tracker import OutcomeTracker
        from animus_forge.state import AgentMemory

        mission_store = MissionStore(backend=backend)
        eval_store = get_eval_store()
        outcome_tracker = OutcomeTracker(backend=backend)
        cross_memory = CrossWorkflowMemory(AgentMemory(backend=backend))
        suite_loader = SuiteLoader()

        # Use live provider if available, else mock evaluator for safety
        try:
            from animus_forge.evaluation.base import ProviderEvaluator
            from animus_forge.providers import get_provider

            provider = get_provider()
            evaluator = ProviderEvaluator(provider=provider)
        except Exception:
            evaluator = AgentEvaluator(agent_fn=lambda x: "mock output")

        eval_runner = EvalRunner(evaluator)
        evidence_bridge = EvidenceBridge(
            eval_store=eval_store,
            outcome_tracker=outcome_tracker,
            cross_memory=cross_memory,
        )
        citizen = ResearchCitizen(
            mission_store=mission_store,
            workflow_engine=state.workflow_engine,
            eval_runner=eval_runner,
            eval_loader=suite_loader,
            evidence_bridge=evidence_bridge,
            guard=state.arete_guard,
        )
        state.citizen_commissioner = CitizenCommissioner(citizen)
        logger.info("Research Citizen commissioner initialized")
    except Exception as e:
        logger.warning("Citizen commissioner not initialized: %s", e)

    # Initialize Mission Scheduler (Phase 5)
    try:
        from animus_forge.missions.store import MissionLedger
        from animus_forge.scheduler import (
            CitizenWorkerPool,
            ContainerConfig,
            ContainerManager,
            CostEnforcer,
            LeaseManager,
            MissionScheduler,
            PoolConfig,
            SchedulerConfig,
        )
        from animus_forge.scheduler.metrics import SchedulerMetrics

        ledger = MissionLedger(backend=backend)
        lease_mgr = LeaseManager(backend=backend, default_ttl_seconds=300)
        cost_enf = CostEnforcer(
            backend=backend,
            default_mission_cap_usd=Decimal("10.00"),
            global_cap_usd=Decimal("100.00"),
        )
        # Optional container isolation (Phase 6)
        container_cfg = ContainerConfig(image=os.getenv("ANIMUS_CITIZEN_IMAGE", "python:3.12-slim"))
        container_mgr = ContainerManager(container_cfg)
        pool_cfg = PoolConfig(max_workers=4)
        if container_mgr.is_available() and os.getenv("ANIMUS_CONTAINER_MODE", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            pool_cfg.isolation_mode = "container"
            logger.info("Container isolation enabled for citizen workers")
        else:
            logger.info("Process isolation enabled for citizen workers")

        pool = CitizenWorkerPool(
            lease_mgr,
            config=pool_cfg,
            container_manager=container_mgr if pool_cfg.isolation_mode == "container" else None,
        )
        metrics = SchedulerMetrics(backend=backend)
        scheduler = MissionScheduler(
            ledger=ledger,
            lease_manager=lease_mgr,
            worker_pool=pool,
            cost_enforcer=cost_enf,
            metrics=metrics,
            config=SchedulerConfig(poll_interval_seconds=5.0),
        )
        state.mission_scheduler = scheduler
        logger.info("Mission scheduler initialized")
    except Exception as e:
        logger.warning("Mission scheduler not initialized: %s", e)
        state.mission_scheduler = None

    # Initialize WebSocket components
    state.ws_manager = ConnectionManager()
    state.ws_broadcaster = Broadcaster(state.ws_manager)

    # Start broadcaster with current event loop
    loop = asyncio.get_running_loop()
    state.ws_broadcaster.start(loop)

    # Register broadcaster callback with execution manager
    state.execution_manager.register_callback(state.ws_broadcaster.create_execution_callback())

    logger.info("WebSocket components initialized")

    # Create coordination bridge once (persistent across supervisor instances)
    try:
        from animus_forge.agents.convergence import create_bridge

        _coordination_bridge = create_bridge()
    except Exception:
        _coordination_bridge = None
    state.coordination_bridge = _coordination_bridge

    # Create coordination event log
    try:
        from animus_forge.agents.convergence import create_event_log

        state.coordination_event_log = create_event_log()
    except Exception:
        state.coordination_event_log = None

    # Initialize consciousness bridge (optional)
    try:
        from animus_forge.budget.manager import BudgetManager as _TokenBudgetManager
        from animus_forge.coordination.consciousness_bridge import (
            ConsciousnessBridge,
            ConsciousnessConfig,
        )

        _cb_provider = None
        try:
            from animus_forge.agents import create_agent_provider as _create_provider

            _cb_provider = _create_provider(
                os.environ.get("DEFAULT_PROVIDER", "ollama"),
            )
        except Exception:
            pass  # Provider not configured — consciousness bridge disabled

        if _cb_provider is not None:
            _cb_config = ConsciousnessConfig(
                enabled=os.environ.get("ANIMUS_CONSCIOUSNESS", "").lower() in ("1", "true", "on"),
                reflections_log_path=settings.base_dir / "logs" / "reflections.jsonl",
                review_queue_path=settings.base_dir / "logs" / "workflow_review_queue.jsonl",
            )
            # Try to create a VersionedGraph for Quorum integration
            _cb_graph = None
            try:
                from animus_quorum import VersionedGraph

                _cb_graph = VersionedGraph()
            except Exception:
                pass  # Quorum not installed — consciousness runs without intent publishing

            state.consciousness_bridge = ConsciousnessBridge(
                provider=_cb_provider,
                budget_manager=_TokenBudgetManager(),
                config=_cb_config,
                graph=_cb_graph,
            )
            state.consciousness_bridge.start()
            logger.info("Consciousness bridge initialized")
    except Exception as e:
        logger.debug("Consciousness bridge not available: %s", e)

    from animus_forge.agents import SupervisorAgent, create_agent_provider

    def create_supervisor(backend=None):
        """Factory function to create Supervisor agent."""
        try:
            provider = create_agent_provider(os.environ.get("DEFAULT_PROVIDER", "ollama"))
            try:
                from animus_forge.agents.convergence import create_checker

                checker = create_checker()
            except Exception:
                checker = None  # Convergence not available

            # Tool registry for builder/tester/reviewer agents
            tool_registry = None
            try:
                from animus_forge.tools.registry import ForgeToolRegistry

                require_approval = os.environ.get("FORGE_WRITE_APPROVAL", "").lower() in (
                    "1",
                    "true",
                    "on",
                )
                tool_registry = ForgeToolRegistry(
                    enable_shell=True,
                    require_write_approval=require_approval,
                    budget_manager=state.budget_manager,
                )
            except Exception:
                pass  # Tool registry not available — supervisor runs without tools

            return SupervisorAgent(
                provider,
                backend=backend or state._app_state.get("backend"),
                convergence_checker=checker,
                coordination_bridge=_coordination_bridge,
                budget_manager=state.budget_manager,
                event_log=state.coordination_event_log,
                tool_registry=tool_registry,
            )
        except Exception as e:
            logger.warning(f"Could not create supervisor: {e}")
            return None

    state.supervisor_factory = create_supervisor
    logger.info("Supervisor factory initialized")

    # Initialize agent infrastructure (optional — never blocks startup)
    try:
        from animus_forge.state.agent_memory import AgentMemory

        state.agent_memory = AgentMemory()
        logger.info("Agent memory initialized")
    except Exception as e:
        logger.debug("Agent memory not available: %s", e)

    try:
        from animus_forge.agents.subagent_manager import SubAgentManager

        state.subagent_manager = SubAgentManager(max_concurrent=8)
        logger.info("SubAgentManager initialized")
    except Exception as e:
        logger.debug("SubAgentManager not available: %s", e)

    try:
        from animus_forge.agents.process_registry import ProcessRegistry

        state.process_registry = ProcessRegistry(
            subagent_manager=state.subagent_manager,
        )
        logger.info("Process registry initialized")
    except Exception as e:
        logger.debug("Process registry not available: %s", e)

    try:
        from animus_forge.agents.task_runner import AgentTaskRunner

        _tr_provider = create_agent_provider(os.environ.get("DEFAULT_PROVIDER", "ollama"))
        _tr_registry = None
        try:
            from animus_forge.tools.registry import ForgeToolRegistry

            _tr_registry = ForgeToolRegistry(
                enable_shell=True,
                budget_manager=state.budget_manager,
            )
        except Exception:
            pass

        state.task_runner = AgentTaskRunner(
            provider=_tr_provider,
            tool_registry=_tr_registry,
            subagent_manager=state.subagent_manager,
            broadcaster=state.ws_broadcaster,
            agent_memory=state.agent_memory,
            budget_manager=state.budget_manager,
        )
        logger.info("AgentTaskRunner initialized")
    except Exception as e:
        logger.debug("AgentTaskRunner not available: %s", e)

    # Load agent YAML configs (optional)
    state.agent_configs = None
    try:
        from animus_forge.agents.config_loader import load_agent_configs

        state.agent_configs = load_agent_configs(base_dir=settings.base_dir)
        logger.info("Agent configs loaded (%d agents)", len(state.agent_configs))
    except Exception as e:
        logger.debug("Agent config loader not available: %s", e)

    # Wire TaskRunner into Supervisor factory so delegated agents get
    # tools, memory, and result tracking automatically
    _original_create_supervisor = create_supervisor

    def _create_supervisor_with_runner(backend=None):
        sup = _original_create_supervisor(backend)
        if sup is not None:
            if state.task_runner is not None:
                sup.set_task_runner(state.task_runner)
            if state.agent_configs is not None:
                sup._agent_configs = state.agent_configs
        return sup

    state.supervisor_factory = _create_supervisor_with_runner
    logger.info("Supervisor factory wired with TaskRunner")

    # Migrate existing workflows (one-time)
    try:
        workflows_dir = settings.workflows_dir
        migrated = state.version_manager.migrate_existing_workflows(workflows_dir)
        if migrated:
            logger.info(f"Migrated {len(migrated)} existing workflows to version control")
    except Exception as e:
        logger.warning(f"Workflow migration skipped: {e}")

    state.schedule_manager.start()

    # Start mission scheduler if initialized
    if state.mission_scheduler:
        try:
            await state.mission_scheduler.start()
            logger.info("Mission scheduler started")
        except Exception as e:
            logger.warning("Mission scheduler failed to start: %s", e)

    # Mark application as ready
    state._app_state["ready"] = True
    logger.info("Application startup complete - ready to serve requests")

    yield

    # Begin graceful shutdown
    logger.info("Beginning graceful shutdown...")
    state._app_state["shutting_down"] = True
    state._app_state["ready"] = False

    # Wait for active requests to complete (with timeout)
    shutdown_timeout = 30  # seconds
    start = time.monotonic()
    while state._app_state["active_requests"] > 0:
        if time.monotonic() - start > shutdown_timeout:
            logger.warning(
                f"Shutdown timeout reached with {state._app_state['active_requests']} "
                "active requests still running"
            )
            break
        await asyncio.sleep(0.1)

    # Shutdown managers
    if state.mission_scheduler:
        try:
            await state.mission_scheduler.stop()
            logger.info("Mission scheduler stopped")
        except Exception as e:
            logger.warning("Mission scheduler stop failed: %s", e)

    state.schedule_manager.shutdown()
    state.job_manager.shutdown()

    # Shutdown WebSocket broadcaster
    if state.ws_broadcaster:
        await state.ws_broadcaster.stop()

    # Stop consciousness bridge
    if state.consciousness_bridge is not None:
        try:
            state.consciousness_bridge.stop()
        except Exception as e:
            logger.warning("Failed to stop consciousness bridge: %s", e)

    # Close coordination bridge
    if _coordination_bridge is not None:
        try:
            _coordination_bridge.close()
        except Exception as e:
            logger.warning("Failed to close coordination bridge: %s", e)

    # Close coordination event log
    if state.coordination_event_log is not None:
        try:
            state.coordination_event_log.close()
        except Exception as e:
            logger.warning("Failed to close coordination event log: %s", e)

    # Reset circuit breakers
    reset_all_circuits()

    logger.info("Graceful shutdown complete")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Workflow Orchestrator", version="0.1.0", lifespan=lifespan)

# CORS middleware — configurable via CORS_ORIGINS env var (comma-separated)
_default_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_cors_origins = (
    os.environ.get("CORS_ORIGINS", "").split(",")
    if os.environ.get("CORS_ORIGINS")
    else _default_origins
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests with timing and request IDs.

    Also tracks active requests for graceful shutdown and rejects new
    requests during shutdown.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Reject requests during shutdown (except health checks)
        path = request.url.path
        if state._app_state["shutting_down"] and not path.startswith("/health"):
            return JSONResponse(
                status_code=503,
                content={"detail": "Service shutting down"},
                headers={"Retry-After": "30"},
            )

        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]

        # Get client info
        client_ip = request.client.host if request.client else "unknown"
        method = request.method

        # Track active requests for graceful shutdown
        await state.increment_active_requests()

        # Log request start with structured fields
        start_time = time.perf_counter()
        logger.info(
            f"[{request_id}] {method} {path} - client={client_ip}",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "client_ip": client_ip,
            },
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error and re-raise
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"[{request_id}] {method} {path} - 500 ERROR in {duration_ms:.1f}ms - {e}",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "status_code": 500,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise
        finally:
            await state.decrement_active_requests()

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response with structured fields
        status_code = response.status_code
        log_level = logging.WARNING if status_code >= 400 else logging.INFO
        logger.log(
            log_level,
            f"[{request_id}] {method} {path} - {status_code} in {duration_ms:.1f}ms",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        # Add request ID to response headers for tracing
        response.headers["X-Request-ID"] = request_id

        return response


# Register middleware (order matters: last added runs first on request)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuditLogMiddleware)

_tracing_settings = get_settings()
if _tracing_settings.tracing_enabled:
    app.add_middleware(
        TracingMiddleware,
        service_name=_tracing_settings.tracing_service_name,
        exclude_paths=["/health", "/health/live", "/health/ready", "/metrics"],
    )

_settings = get_settings()
brute_force_config = BruteForceConfig(
    max_attempts_per_minute=_settings.brute_force_max_attempts_per_minute,
    max_attempts_per_hour=_settings.brute_force_max_attempts_per_hour,
    max_auth_attempts_per_minute=_settings.brute_force_max_auth_attempts_per_minute,
    max_auth_attempts_per_hour=_settings.brute_force_max_auth_attempts_per_hour,
    initial_block_seconds=_settings.brute_force_initial_block_seconds,
    max_block_seconds=_settings.brute_force_max_block_seconds,
    auth_paths=("/v1/auth/", "/auth/", "/login"),
)
app.add_middleware(BruteForceMiddleware, protection=get_brute_force_protection(brute_force_config))

request_limit_config = RequestLimitConfig(
    max_body_size=_settings.request_max_body_size,
    max_json_size=_settings.request_max_json_size,
    max_form_size=_settings.request_max_form_size,
    large_upload_paths=(),
)
app.add_middleware(RequestSizeLimitMiddleware, config=request_limit_config)

# Register rate limiter
app.state.limiter = state.limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceeded errors with structured response."""
    request_id = request.headers.get("X-Request-ID")
    response = RateLimitErrorResponse(
        error={
            "error_code": "RATE_LIMITED",
            "message": "Rate limit exceeded",
            "details": {"limit": str(exc.detail)},
            "request_id": request_id,
        },
        retry_after=int(exc.detail) if str(exc.detail).isdigit() else 60,
    )
    return JSONResponse(
        status_code=429,
        content=response.model_dump(),
        headers={"Retry-After": str(exc.detail)},
    )


app.add_exception_handler(AnimusForgeError, animus_forge_exception_handler)
app.add_exception_handler(APIException, api_exception_handler)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from animus_forge.api_routes import (  # noqa: E402
    agents,
    auth,
    budgets,
    citizens,
    coordination,
    dashboard,
    evals,
    executions,
    graph,
    health,
    history,
    jobs,
    mcp,
    mission_scheduler,
    prompts,
    schedules,
    settings,
    webhooks,
    websocket,
    workflows,
)

v1_router = APIRouter(prefix="/v1", tags=["v1"])
v1_router.include_router(auth.router)
v1_router.include_router(workflows.router)
v1_router.include_router(executions.router)
v1_router.include_router(schedules.router)
v1_router.include_router(webhooks.router)
v1_router.include_router(mcp.router)
v1_router.include_router(jobs.router)
v1_router.include_router(prompts.router)
v1_router.include_router(settings.router)
v1_router.include_router(budgets.router)
v1_router.include_router(dashboard.router)
v1_router.include_router(history.router)
v1_router.include_router(graph.router)
v1_router.include_router(coordination.router)
v1_router.include_router(agents.router)
v1_router.include_router(citizens.router)
v1_router.include_router(mission_scheduler.router)
v1_router.include_router(evals.router)

app.include_router(v1_router)
app.include_router(health.router)
app.include_router(webhooks.trigger_router)
app.include_router(websocket.router)

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Animus Forge API server")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind socket to this host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Bind socket to this port (default: 8000)"
    )
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of worker processes (default: 1)"
    )
    args = parser.parse_args()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
    )
