"""Конфигурация сервиса Analyzer.

Все параметры читаются из переменных окружения с префиксом ``CM_``.
Вложенные секции разделяются двойным подчёркиванием (``__``), например::

    CM_ANALYZER__INTERVAL_SECONDS=900
    CM_ANALYZER__GRACE__ARRIVAL_MINUTES=120
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GraceConfig(BaseSettings):
    """Поблажки на перегонку техники между этапами (в минутах).

    * ``arrival_minutes`` — сколько ждать появления required-техники
      после старта этапа, прежде чем ругаться на ``missing_required``.
    * ``departure_minutes`` — сколько разрешено уезжать технике
      предыдущего этапа, прежде чем ругаться на ``unexpected_equipment``.
    """

    arrival_minutes: int = 60
    departure_minutes: int = 60


class AnalyzerConfig(BaseSettings):
    """Параметры одного прохода Analyzer по участкам."""

    #: Период запуска планировщика.
    interval_seconds: int = 3600

    #: За сколько последних минут собирать детекции.
    analysis_window_minutes: int = 60

    #: Порог уверенности детектора.
    min_confidence: float = 0.5

    #: Сколько раз подряд должно сработать условие, чтобы повысить severity.
    min_hits: int = 2

    #: Максимум кадров, которые мы прикладываем к отклонению как доказательство.
    max_evidence_frames: int = 5

    #: Настройки grace-периодов.
    grace: GraceConfig = Field(default_factory=GraceConfig)


class Settings(BaseSettings):
    """Корневые настройки сервиса.

    Собирает всё, что нужно для подключения к БД, логирования и работы
    Analyzer. Читается один раз при старте процесса.
    """

    model_config = SettingsConfigDict(
        env_prefix="CM_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    #: DSN подключения к PostgreSQL. По умолчанию указывает на контейнер
    #: ``db`` в той же docker-сети — как в ``docs_ARCHITECTURE.md``.
    database_url: str = (
        "postgresql://cm_admin:admin_password@localhost:54321/construction_monitoring"
    )

    log_level: str = "INFO"

    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)


def load_settings() -> Settings:
    """Точка входа для чтения конфигурации.

    Возвращает готовый объект :class:`Settings`. Вынесено в функцию,
    чтобы тесты могли подменять источник данных.
    """
    return Settings()