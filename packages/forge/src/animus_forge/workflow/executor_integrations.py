"""Application-owned service clients for Kernel integration handlers."""

from importlib import import_module

from animus_kernel.executor.executor_integrations import (
    IntegrationHandlersMixin as KernelIntegrationHandlersMixin,
)


class IntegrationHandlersMixin(KernelIntegrationHandlersMixin):
    def _integration_dependency(self, module: str, name: str):
        return getattr(import_module(f"animus_forge.{module}"), name)

    def _integration_settings(self):
        from animus_forge.config import get_settings

        return get_settings()
