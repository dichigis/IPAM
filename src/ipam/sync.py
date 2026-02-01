"""
Модуль синхронизации маршрутов - сравнение Golden RIB с фактическими данными.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Set

from .golden_rib import Route, GoldenRIB

logger = logging.getLogger(__name__)


class SyncAction(Enum):
    """Действие синхронизации."""
    ADD = "add"
    DELETE = "delete"


@dataclass
class SyncInstruction:
    """Инструкция по синхронизации маршрута."""
    action: SyncAction
    route: Route

    def __repr__(self) -> str:
        return f"SyncInstruction({self.action.value}: {self.route.prefix} via {self.route.interface})"


@dataclass
class SyncResult:
    """Результат сравнения Golden RIB с фактическими маршрутами."""
    node_id: str
    in_sync: bool
    missing_routes: List[Route]  # Есть в Golden RIB, но нет на устройстве
    extra_routes: List[Route]    # Есть на устройстве, но нет в Golden RIB
    instructions: List[SyncInstruction]

    def __repr__(self) -> str:
        status = "IN_SYNC" if self.in_sync else "OUT_OF_SYNC"
        return (
            f"SyncResult({self.node_id}: {status}, "
            f"missing={len(self.missing_routes)}, extra={len(self.extra_routes)})"
        )


class RouteSynchronizer:
    """Синхронизатор маршрутов - сравнивает Golden RIB с фактическими данными."""

    def compare(
        self,
        golden_rib: GoldenRIB,
        actual_routes: List[Route],
        af: str = "ipv4"
    ) -> SyncResult:
        """
        Сравнивает Golden RIB с фактическими маршрутами.

        Args:
            golden_rib: Эталонная таблица маршрутизации
            actual_routes: Фактические маршруты с устройства
            af: Address family (ipv4 или ipv6)

        Returns:
            Результат сравнения с инструкциями по синхронизации
        """
        logger.info(f"Сравнение маршрутов для узла {golden_rib.node_id}, af={af}")

        # Получаем golden маршруты для нужного AF
        if af == "ipv4":
            golden_routes = golden_rib.ipv4_routes
        else:
            golden_routes = golden_rib.ipv6_routes

        # Строим индексы по префиксам
        golden_by_prefix: Dict[str, Route] = {r.prefix: r for r in golden_routes}
        actual_by_prefix: Dict[str, Route] = {r.prefix: r for r in actual_routes}

        golden_prefixes: Set[str] = set(golden_by_prefix.keys())
        actual_prefixes: Set[str] = set(actual_by_prefix.keys())

        # Находим расхождения
        missing_prefixes = golden_prefixes - actual_prefixes
        extra_prefixes = actual_prefixes - golden_prefixes

        missing_routes = [golden_by_prefix[p] for p in missing_prefixes]
        extra_routes = [actual_by_prefix[p] for p in extra_prefixes]

        # Формируем инструкции
        instructions: List[SyncInstruction] = []

        # Добавить недостающие маршруты
        for route in missing_routes:
            instructions.append(SyncInstruction(
                action=SyncAction.ADD,
                route=route
            ))
            logger.debug(f"Инструкция: ADD {route.prefix} via {route.interface}")

        # Удалить лишние маршруты
        for route in extra_routes:
            instructions.append(SyncInstruction(
                action=SyncAction.DELETE,
                route=route
            ))
            logger.debug(f"Инструкция: DELETE {route.prefix} via {route.interface}")

        in_sync = len(instructions) == 0

        result = SyncResult(
            node_id=golden_rib.node_id,
            in_sync=in_sync,
            missing_routes=missing_routes,
            extra_routes=extra_routes,
            instructions=instructions
        )

        if in_sync:
            logger.info(f"Узел {golden_rib.node_id} в синхронизации")
        else:
            logger.warning(
                f"Узел {golden_rib.node_id} НЕ в синхронизации: "
                f"{len(missing_routes)} отсутствующих, {len(extra_routes)} лишних маршрутов"
            )

        return result

    def compare_all(
        self,
        golden_rib: GoldenRIB,
        actual_ipv4_routes: List[Route],
        actual_ipv6_routes: List[Route]
    ) -> Dict[str, SyncResult]:
        """
        Сравнивает Golden RIB с фактическими маршрутами для обоих AF.

        Returns:
            Словарь с результатами для каждого AF
        """
        return {
            "ipv4": self.compare(golden_rib, actual_ipv4_routes, "ipv4"),
            "ipv6": self.compare(golden_rib, actual_ipv6_routes, "ipv6"),
        }
