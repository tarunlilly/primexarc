"""
Governance Module - Alerts

Provides alert generation and notification for policy violations.

Implements DRY principle: Reuses PolicyViolation and evaluations for alert
creation, extensible for different alert channels.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta

from primedata.utils.log_utils import get_logger

from .policy_engine import (
    PolicyViolation,
    PolicySeverity,
    PolicyStatus,
    PolicyEvaluationResult,
)

logger = get_logger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class AlertChannel(str, Enum):
    """Alert delivery channels."""

    LOG = "log"  # Write to application log
    EMAIL = "email"  # Send via email
    WEBHOOK = "webhook"  # POST to webhook URL
    SLACK = "slack"  # Send to Slack
    DATABASE = "database"  # Store in database


class AlertPriority(str, Enum):
    """Alert priority levels."""

    LOW = "low"  # Low priority
    MEDIUM = "medium"  # Medium priority
    HIGH = "high"  # High priority
    CRITICAL = "critical"  # Critical priority


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class AlertRule:
    """Rule for triggering alerts on policy violations."""

    rule_id: str
    name: str
    description: str
    policy_id: Optional[str] = None  # Alert on specific policy, or None for all
    min_severity: PolicySeverity = PolicySeverity.WARNING
    channels: List[AlertChannel] = field(default_factory=list)
    priority: AlertPriority = AlertPriority.MEDIUM
    enabled: bool = True
    cooldown_minutes: int = 0  # Minutes to wait before re-alerting same violation

    def should_alert(self, violation: PolicyViolation) -> bool:
        """
        Check if violation should trigger alert.

        Args:
            violation: PolicyViolation to check

        Returns:
            True if alert should be triggered, False otherwise
        """
        if not self.enabled:
            return False

        # Check policy filter
        if self.policy_id and violation.policy_id != self.policy_id:
            return False

        # Check severity threshold
        severity_order = {
            PolicySeverity.INFO: 0,
            PolicySeverity.WARNING: 1,
            PolicySeverity.ERROR: 2,
            PolicySeverity.CRITICAL: 3,
        }
        return severity_order.get(violation.severity, 0) >= severity_order.get(
            self.min_severity, 0
        )


@dataclass
class Alert:
    """Represents an alert generated from policy violations."""

    alert_id: str
    rule_id: str
    title: str
    message: str
    severity: PolicySeverity
    priority: AlertPriority
    violation: PolicyViolation
    channels: List[AlertChannel] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_to: Dict[AlertChannel, bool] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"Alert[{self.priority.value}]: {self.title} - {self.message}"


# ============================================================================
# ALERT GENERATOR
# ============================================================================


class AlertGenerator:
    """
    Generates and manages alerts from policy violations.

    KISS principle: Simple alert creation from violations, extensible
    handlers for different channels.
    """

    def __init__(self):
        """Initialize alert generator."""
        self.rules: Dict[str, AlertRule] = {}
        self.alert_handlers: Dict[AlertChannel, Callable] = {}
        self.alert_history: List[Alert] = []
        self.last_alert_time: Dict[str, datetime] = {}
        logger.debug("AlertGenerator initialized")

    def register_rule(self, rule: AlertRule) -> None:
        """
        Register an alert rule.

        Args:
            rule: AlertRule to register
        """
        self.rules[rule.rule_id] = rule
        logger.debug(f"Alert rule registered: {rule.rule_id} ({rule.name})")

    def register_handler(
        self, channel: AlertChannel, handler: Callable[[Alert], bool]
    ) -> None:
        """
        Register a handler for a specific alert channel.

        Args:
            channel: AlertChannel to handle
            handler: Callable that accepts Alert and returns True if sent successfully
        """
        self.alert_handlers[channel] = handler
        logger.debug(f"Alert handler registered for channel: {channel.value}")

    def generate_alert(
        self, rule: AlertRule, violation: PolicyViolation
    ) -> Optional[Alert]:
        """
        Generate an alert from a violation.

        Args:
            rule: AlertRule that triggered
            violation: PolicyViolation that triggered the rule

        Returns:
            Alert object or None if alert should be suppressed
        """
        # Check cooldown
        alert_key = f"{rule.rule_id}:{violation.resource_id}"
        last_time = self.last_alert_time.get(alert_key)
        if last_time:
            elapsed = (datetime.utcnow() - last_time).total_seconds() / 60
            if elapsed < rule.cooldown_minutes:
                logger.debug(
                    f"Alert suppressed due to cooldown: {alert_key} "
                    f"(elapsed: {elapsed:.1f}min, cooldown: {rule.cooldown_minutes}min)"
                )
                return None

        # Generate unique alert ID
        timestamp = datetime.utcnow().timestamp()
        alert_id = f"alert_{int(timestamp * 1000)}_{violation.resource_id[:10]}"

        alert = Alert(
            alert_id=alert_id,
            rule_id=rule.rule_id,
            title=rule.name,
            message=f"{violation.policy_name}: {violation.message}",
            severity=violation.severity,
            priority=rule.priority,
            violation=violation,
            channels=rule.channels.copy(),
            metadata={
                "policy_id": violation.policy_id,
                "resource_id": violation.resource_id,
                "resource_type": violation.resource_type,
            },
        )

        logger.info(f"Alert generated: {alert}")
        self.last_alert_time[alert_key] = datetime.utcnow()

        return alert

    def process_violations(
        self, violations: List[PolicyViolation]
    ) -> List[Alert]:
        """
        Process violations and generate alerts.

        Args:
            violations: List of PolicyViolation objects

        Returns:
            List of generated Alert objects
        """
        alerts = []

        for violation in violations:
            for rule in self.rules.values():
                if not rule.should_alert(violation):
                    continue

                alert = self.generate_alert(rule, violation)
                if alert:
                    alerts.append(alert)

        logger.debug(f"Processed {len(violations)} violations, generated {len(alerts)} alerts")
        return alerts

    def send_alert(self, alert: Alert) -> Dict[AlertChannel, bool]:
        """
        Send alert through configured channels.

        Args:
            alert: Alert to send

        Returns:
            Dictionary mapping AlertChannel to success bool
        """
        results = {}

        for channel in alert.channels:
            if channel not in self.alert_handlers:
                logger.warning(f"No handler registered for channel: {channel.value}")
                results[channel] = False
                continue

            handler = self.alert_handlers[channel]
            try:
                success = handler(alert)
                results[channel] = success
                alert.sent_to[channel] = success

                if success:
                    logger.debug(f"Alert sent to {channel.value}: {alert.alert_id}")
                else:
                    logger.warning(f"Failed to send alert to {channel.value}: {alert.alert_id}")
            except Exception as e:
                logger.error(f"Error sending alert to {channel.value}: {e}")
                results[channel] = False
                alert.sent_to[channel] = False

        self.alert_history.append(alert)
        return results

    def send_alerts(self, alerts: List[Alert]) -> Dict[str, Dict[AlertChannel, bool]]:
        """
        Send multiple alerts.

        Args:
            alerts: List of Alert objects

        Returns:
            Dictionary mapping alert_id to channel results
        """
        results = {}
        for alert in alerts:
            results[alert.alert_id] = self.send_alert(alert)
        return results

    def get_recent_alerts(
        self, minutes: int = 60, severity: Optional[PolicySeverity] = None
    ) -> List[Alert]:
        """
        Get recent alerts.

        Args:
            minutes: Look back this many minutes
            severity: Filter by severity, or None for all

        Returns:
            List of recent alerts
        """
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        alerts = [a for a in self.alert_history if a.created_at >= cutoff]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return alerts

    def get_alert_summary(self) -> Dict[str, Any]:
        """
        Get summary of alerts.

        Returns:
            Summary dictionary with counts and status
        """
        total = len(self.alert_history)
        by_severity = {}
        for sev in PolicySeverity:
            by_severity[sev.value] = sum(1 for a in self.alert_history if a.severity == sev)

        by_channel = {}
        for channel in AlertChannel:
            by_channel[channel.value] = sum(
                1 for a in self.alert_history if channel in a.channels
            )

        return {
            "total_alerts": total,
            "by_severity": by_severity,
            "by_channel": by_channel,
            "active_rules": sum(1 for r in self.rules.values() if r.enabled),
        }


# ============================================================================
# DEFAULT ALERT HANDLERS
# ============================================================================


def default_log_handler(alert: Alert) -> bool:
    """Default handler that logs alerts."""
    logger.warning(f"[ALERT] {alert}")
    return True


def default_email_handler(alert: Alert) -> bool:
    """Default handler for email alerts (placeholder)."""
    # TODO: Implement email sending
    logger.info(f"[EMAIL] Would send alert to configured recipients: {alert.alert_id}")
    return True


def default_webhook_handler(alert: Alert) -> bool:
    """Default handler for webhook alerts (placeholder)."""
    # TODO: Implement webhook POST
    logger.info(f"[WEBHOOK] Would POST alert to configured webhook: {alert.alert_id}")
    return True


def default_slack_handler(alert: Alert) -> bool:
    """Default handler for Slack alerts (placeholder)."""
    # TODO: Implement Slack message
    logger.info(f"[SLACK] Would send alert to configured Slack channel: {alert.alert_id}")
    return True
