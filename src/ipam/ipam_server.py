"""
IPAM Server - серверное приложение для управления маршрутизацией.
Читает SoT, формирует Golden RIB, подключается к агентам на узлах,
сравнивает маршруты и отправляет инструкции по синхронизации.
"""
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import grpc

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))
from proto_gen import ipam_pb2
from proto_gen import ipam_pb2_grpc

from .golden_rib import GoldenRIB, Route, SoTReader
from .sync import RouteSynchronizer, SyncAction, SyncResult

logger = logging.getLogger(__name__)


@dataclass
class NodeConfig:
    """Конфигурация подключения к узлу."""
    node_id: str
    address: str  # host:port


class IPAMServer:
    """IPAM сервер - управление маршрутизацией."""

    def __init__(self, sot_path: Path, nodes_config_path: Optional[Path] = None):
        """
        Args:
            sot_path: Путь к файлу SoT
            nodes_config_path: Путь к конфигурации узлов (адреса агентов)
        """
        self.sot_path = sot_path
        self.nodes_config_path = nodes_config_path
        self.sot_reader = SoTReader(sot_path)
        self.synchronizer = RouteSynchronizer()
        self._nodes_config: Dict[str, NodeConfig] = {}
        self._golden_ribs: Dict[str, GoldenRIB] = {}

    def load(self) -> None:
        """Загружает данные SoT и конфигурацию узлов."""
        logger.info("Загрузка IPAM Server")

        # Загружаем SoT и строим Golden RIB
        self._golden_ribs = self.sot_reader.build_golden_ribs()
        logger.info(f"Загружено {len(self._golden_ribs)} Golden RIB")

        # Загружаем конфигурацию узлов
        if self.nodes_config_path and self.nodes_config_path.exists():
            self._load_nodes_config()

    def _load_nodes_config(self) -> None:
        """Загружает конфигурацию подключения к узлам."""
        logger.info(f"Загрузка конфигурации узлов из {self.nodes_config_path}")
        with open(self.nodes_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        for node_id, node_data in config.get("nodes", {}).items():
            self._nodes_config[node_id] = NodeConfig(
                node_id=node_id,
                address=node_data.get("address", f"localhost:50051")
            )
        logger.info(f"Загружено {len(self._nodes_config)} конфигураций узлов")

    def get_golden_rib(self, node_id: str) -> Optional[GoldenRIB]:
        """Возвращает Golden RIB для узла."""
        return self._golden_ribs.get(node_id)

    def get_all_node_ids(self) -> List[str]:
        """Возвращает список всех node_id."""
        return list(self._golden_ribs.keys())

    def _connect_to_node(self, node_id: str) -> Optional[ipam_pb2_grpc.NodeAgentStub]:
        """Создаёт gRPC клиент для подключения к агенту узла."""
        config = self._nodes_config.get(node_id)
        if not config:
            logger.warning(f"Нет конфигурации для узла {node_id}")
            return None

        logger.info(f"Подключение к узлу {node_id} по адресу {config.address}")
        try:
            channel = grpc.insecure_channel(config.address)
            stub = ipam_pb2_grpc.NodeAgentStub(channel)
            return stub
        except Exception as e:
            logger.error(f"Ошибка подключения к узлу {node_id}: {e}")
            return None

    def _fetch_routes_from_node(
        self, stub: ipam_pb2_grpc.NodeAgentStub, af: str = "ipv4"
    ) -> List[Route]:
        """Получает маршруты с узла через gRPC."""
        af_enum = ipam_pb2.AF_IPV4 if af == "ipv4" else ipam_pb2.AF_IPV6
        request = ipam_pb2.GetRoutesRequest(af=af_enum)

        try:
            response = stub.GetRoutes(request, timeout=10)
            routes = []
            for proto_route in response.routes:
                route_type = (
                    "connected"
                    if proto_route.route_type == ipam_pb2.ROUTE_TYPE_CONNECTED
                    else "static"
                )
                routes.append(Route(
                    prefix=proto_route.prefix,
                    interface=proto_route.interface,
                    route_type=route_type,
                    role=proto_route.role,
                    description=proto_route.description,
                ))
            logger.info(f"Получено {len(routes)} {af} маршрутов с узла {response.node_id}")
            return routes
        except grpc.RpcError as e:
            logger.error(f"gRPC ошибка при получении маршрутов: {e}")
            return []

    def _apply_changes_to_node(
        self,
        stub: ipam_pb2_grpc.NodeAgentStub,
        sync_result: SyncResult,
        af: str = "ipv4"
    ) -> bool:
        """Применяет изменения к узлу через gRPC."""
        if sync_result.in_sync:
            logger.info(f"Узел {sync_result.node_id} в синхронизации, изменения не требуются")
            return True

        instructions = []
        af_enum = ipam_pb2.AF_IPV4 if af == "ipv4" else ipam_pb2.AF_IPV6

        for sync_inst in sync_result.instructions:
            action = (
                ipam_pb2.ROUTE_ACTION_ADD
                if sync_inst.action == SyncAction.ADD
                else ipam_pb2.ROUTE_ACTION_DELETE
            )
            route_type = (
                ipam_pb2.ROUTE_TYPE_CONNECTED
                if sync_inst.route.route_type == "connected"
                else ipam_pb2.ROUTE_TYPE_STATIC
            )
            proto_route = ipam_pb2.Route(
                prefix=sync_inst.route.prefix,
                interface=sync_inst.route.interface,
                route_type=route_type,
                role=sync_inst.route.role,
                description=sync_inst.route.description,
                af=af_enum,
            )
            instructions.append(ipam_pb2.RouteInstruction(action=action, route=proto_route))

        request = ipam_pb2.ApplyChangesRequest(instructions=instructions)

        try:
            response = stub.ApplyChanges(request, timeout=30)
            if response.success:
                logger.info(f"Изменения успешно применены к узлу {sync_result.node_id}")
            else:
                for result in response.results:
                    if not result.success:
                        logger.error(
                            f"Ошибка применения маршрута {result.route.prefix}: "
                            f"{result.error_message}"
                        )
            return response.success
        except grpc.RpcError as e:
            logger.error(f"gRPC ошибка при применении изменений: {e}")
            return False

    def sync_node(self, node_id: str, apply_changes: bool = False) -> Optional[Dict[str, SyncResult]]:
        """
        Синхронизирует один узел с Golden RIB.

        Args:
            node_id: Идентификатор узла
            apply_changes: Применить ли изменения

        Returns:
            Результаты синхронизации для IPv4 и IPv6, или None при ошибке
        """
        logger.info(f"Синхронизация узла {node_id}, apply_changes={apply_changes}")

        golden_rib = self.get_golden_rib(node_id)
        if not golden_rib:
            logger.error(f"Golden RIB для узла {node_id} не найден")
            return None

        stub = self._connect_to_node(node_id)
        if not stub:
            return None

        results = {}

        # Синхронизация IPv4
        actual_ipv4 = self._fetch_routes_from_node(stub, "ipv4")
        sync_ipv4 = self.synchronizer.compare(golden_rib, actual_ipv4, "ipv4")
        results["ipv4"] = sync_ipv4

        if apply_changes and not sync_ipv4.in_sync:
            self._apply_changes_to_node(stub, sync_ipv4, "ipv4")

        # Синхронизация IPv6
        actual_ipv6 = self._fetch_routes_from_node(stub, "ipv6")
        sync_ipv6 = self.synchronizer.compare(golden_rib, actual_ipv6, "ipv6")
        results["ipv6"] = sync_ipv6

        if apply_changes and not sync_ipv6.in_sync:
            self._apply_changes_to_node(stub, sync_ipv6, "ipv6")

        return results

    def sync_all_nodes(self, apply_changes: bool = False) -> Dict[str, Dict[str, SyncResult]]:
        """
        Синхронизирует все узлы с Golden RIB.

        Args:
            apply_changes: Применить ли изменения

        Returns:
            Результаты синхронизации для каждого узла
        """
        logger.info(f"Синхронизация всех узлов, apply_changes={apply_changes}")
        results = {}

        for node_id in self._nodes_config.keys():
            node_results = self.sync_node(node_id, apply_changes)
            if node_results:
                results[node_id] = node_results

        return results

    def print_golden_rib(self, node_id: str) -> None:
        """Выводит Golden RIB для узла (для отладки)."""
        rib = self.get_golden_rib(node_id)
        if not rib:
            print(f"Golden RIB для {node_id} не найден")
            return

        print(f"\n=== Golden RIB для {node_id} ({rib.node_name}) ===")
        print("\nIPv4 маршруты:")
        for route in rib.ipv4_routes:
            print(f"  {route.prefix:20s} via {route.interface:15s} [{route.route_type}] {route.role}")

        print("\nIPv6 маршруты:")
        for route in rib.ipv6_routes:
            print(f"  {route.prefix:30s} via {route.interface:15s} [{route.route_type}] {route.role}")
