"""Bridge manager for routing events to messaging platforms.

The manager maintains a registry of active bridges and routes events to the
appropriate platform based on session configuration.
"""

import structlog

from tether.bridges.base import ApprovalRequest, BridgeInterface

logger = structlog.get_logger(__name__)


class BridgeManager:
    """Manages messaging platform bridges and routes events.

    Bridges are registered at startup based on available credentials.
    Events are routed to the platform associated with each session.
    """

    def __init__(self) -> None:
        self._bridges: dict[str, BridgeInterface] = {}

    def register_bridge(self, platform: str, bridge: BridgeInterface) -> None:
        """Register a messaging platform bridge.

        Args:
            platform: Platform identifier (e.g., "telegram", "slack", "discord").
            bridge: Bridge implementation instance.
        """
        self._bridges[platform] = bridge
        logger.info("Bridge registered", platform=platform)

    def get_bridge(self, platform: str) -> BridgeInterface | None:
        """Get a registered bridge by platform name.

        Args:
            platform: Platform identifier.

        Returns:
            Bridge instance or None if not registered.
        """
        return self._bridges.get(platform)

    def list_bridges(self) -> list[str]:
        """List all registered platform names.

        Returns:
            List of platform identifiers.
        """
        return list(self._bridges.keys())

    async def route_output(
        self, session_id: str, text: str, platform: str, metadata: dict | None = None
    ) -> None:
        """Route output text to the appropriate platform bridge.

        Args:
            session_id: Internal Tether session ID.
            text: Output text (markdown format).
            platform: Target platform identifier.
            metadata: Optional metadata about the output.
        """
        bridge = self._bridges.get(platform)
        if not bridge:
            logger.warning(
                "No bridge registered for platform",
                platform=platform,
                session_id=session_id,
            )
            return

        await bridge.on_output(session_id, text, metadata)

    async def route_approval(
        self, session_id: str, request: ApprovalRequest, platform: str
    ) -> None:
        """Route approval request to the appropriate platform bridge.

        Args:
            session_id: Internal Tether session ID.
            request: Approval request details.
            platform: Target platform identifier.
        """
        bridge = self._bridges.get(platform)
        if not bridge:
            logger.warning(
                "No bridge registered for platform",
                platform=platform,
                session_id=session_id,
            )
            return

        await bridge.on_approval_request(session_id, request)

    async def route_status(
        self, session_id: str, status: str, platform: str, metadata: dict | None = None
    ) -> None:
        """Route status change to the appropriate platform bridge.

        Args:
            session_id: Internal Tether session ID.
            status: New status.
            platform: Target platform identifier.
            metadata: Optional metadata about the status.
        """
        bridge = self._bridges.get(platform)
        if not bridge:
            logger.warning(
                "No bridge registered for platform",
                platform=platform,
                session_id=session_id,
            )
            return

        await bridge.on_status_change(session_id, status, metadata)

    async def create_thread(
        self, session_id: str, session_name: str, platform: str
    ) -> dict:
        """Create a messaging thread on the specified platform.

        Args:
            session_id: Internal Tether session ID.
            session_name: Display name for the session.
            platform: Target platform identifier.

        Returns:
            Dict with platform-specific thread info.

        Raises:
            ValueError: If platform is not registered.
        """
        bridge = self._bridges.get(platform)
        if not bridge:
            raise ValueError(f"No bridge registered for platform: {platform}")

        return await bridge.create_thread(session_id, session_name)


# Global bridge manager instance
bridge_manager = BridgeManager()
