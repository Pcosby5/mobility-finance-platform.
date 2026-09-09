"""Versioned demo policy for telemetry alert rules."""

# Speed above which a SPEEDING alert is raised (km/h).
SPEEDING_THRESHOLD_KPH = 120
# Battery at or below which a LOW_BATTERY alert is raised (percent).
LOW_BATTERY_PERCENT = 20
# Silence longer than this window raises an OFFLINE alert (minutes).
OFFLINE_AFTER_MINUTES = 30
