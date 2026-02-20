import asyncio
import logging

# from typing import Any, Dict, List, Optional (Unused)


class DriftAuditor:
    """
    Proactive State Integrity Monitor (Phase 102).

    Monitors high-level state (Balance, Position Count) to detect
    desynchronization without the heavy overhead of full reconciliation.
    Triggers full reconciliation cycles if significant drift is detected, providing "Auto-Healing" capabilities.

    Phase 243: CB-aware skip + timeout wrapper to prevent event loop starvation
    when rest_account_api circuit breaker is OPEN.
    """

    def __init__(self, exchange_adapter, position_tracker, reconciliation_service, balance_manager):
        self.adapter = exchange_adapter
        self.tracker = position_tracker
        self.recon = reconciliation_service
        self.balance_manager = balance_manager
        self.logger = logging.getLogger("DriftAuditor")

        self.running = False
        self._audit_task = None
        self.audit_interval = 60  # Check every 60s
        self.drift_threshold_usd = 1.0  # Alert/Heal if balance drift > $1
        self.recon_cooldown = 120  # Minimum 2 mins between full recons
        self.last_recon_time = 0
        self._audit_timeout = 15.0  # Phase 243: Max seconds per audit cycle

    async def start(self):
        """Starts the background audit loop."""
        if self.running:
            return

        self.running = True
        self._audit_task = asyncio.create_task(self._audit_loop())
        self.logger.info("🛡️ DriftAuditor started (Interval: %ds)", self.audit_interval)

    async def stop(self):
        """Stops the background audit loop."""
        self.running = False
        if self._audit_task:
            self._audit_task.cancel()
            try:
                await self._audit_task
            except asyncio.CancelledError:
                pass
        self.logger.info("🛡️ DriftAuditor stopped")

    def _is_account_cb_open(self) -> bool:
        """Phase 243: Check if rest_account_api circuit breaker is OPEN.
        Returns True if CB is open (skip audit), False if healthy or unknown.
        """
        try:
            connector = self.adapter.connector
            if hasattr(connector, "error_handler"):
                cb = connector.error_handler.get_circuit_breaker("rest_account_api")
                return cb.is_open
        except Exception:
            pass
        return False

    async def _audit_loop(self):
        """Main audit loop."""
        while self.running:
            try:
                await asyncio.sleep(self.audit_interval)

                # Phase 243: Skip audit if account API CB is OPEN
                # This prevents event loop starvation from retry backoffs
                if self._is_account_cb_open():
                    self.logger.debug("⏭️ Skipping audit: rest_account_api CB is OPEN")
                    continue

                await asyncio.wait_for(self.perform_audit(), timeout=self._audit_timeout)
            except asyncio.TimeoutError:
                self.logger.warning("⏰ State Audit timed out (%.0fs)", self._audit_timeout)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("❌ DriftAuditor error: %s", e)
                await asyncio.sleep(10)

    async def perform_audit(self):
        """
        Performs a lightweight state audit.
        If drift is detected, triggers Auto-Healing (Full Reconciliation).
        """
        self.logger.debug("🕵️ Performing State Audit...")

        # 1. Fetch Exchange Summary (Lightweight)
        try:
            balance_data = await self.adapter.connector.fetch_balance()
            ex_balance = balance_data.get("total", {}).get("USDT", 0.0)

            # 2. Match with Local State
            local_balance = self.balance_manager.get_balance()

            # 3. Calculate Drift
            drift = abs(ex_balance - local_balance)

            if drift > self.drift_threshold_usd:
                now = asyncio.get_event_loop().time()
                if now - self.last_recon_time < self.recon_cooldown:
                    self.logger.info(
                        f"⏭️ Drift detected (${drift:.2f}) but skipping Auto-Healing (Cooldown: {int(self.recon_cooldown - (now - self.last_recon_time))}s remaining)"
                    )
                    return

                self.logger.warning(
                    f"⚠️ DRIFT DETECTED: Exchange=${ex_balance:.2f} | Local=${local_balance:.2f} | "
                    f"Diff=${drift:.4f}. Initiating Auto-Healing..."
                )
                self.last_recon_time = now
                await self.recon.reconcile_all()
                return

            # 4. Position Count Audit
            positions = await self.adapter.connector.fetch_positions()
            ex_pos_count = len([p for p in positions if float(p.get("contracts", 0) or p.get("size", 0)) != 0])
            local_pos_count = len(self.tracker.open_positions)

            if ex_pos_count != local_pos_count:
                now = asyncio.get_event_loop().time()
                if now - self.last_recon_time < self.recon_cooldown:
                    self.logger.info(
                        f"⏭️ Pos count drift ({ex_pos_count} vs {local_pos_count}) but skipping Auto-Healing (Cooldown: {int(self.recon_cooldown - (now - self.last_recon_time))}s remaining)"
                    )
                    return

                self.logger.warning(
                    f"⚠️ POS COUNT DRIFT: Exchange={ex_pos_count} | Local={local_pos_count}. "
                    "Initiating Auto-Healing..."
                )
                self.last_recon_time = now
                await self.recon.reconcile_all()
                return

            self.logger.debug("✅ State Audit Passed: No drift detected.")

        except Exception as e:
            self.logger.warning(f"⚠️ State Audit failed (Exchange Error): {e}")
