"""Adapter package — concrete implementations of ``sentinelq.ports``.

Naming convention: ``<source>_<port>.py``
- ``kis_broker.py`` — BrokerPort over KIS REST
- ``kis_data.py``   — DataPort over KIS daily cache + live REST
- ``sim_clock.py``  — ClockPort for backtests
- ``real_clock.py`` — ClockPort for paper/live
"""
