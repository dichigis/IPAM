"""
Golden RIB module - формирование эталонной таблицы маршрутизации из SoT.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """Представление маршрута."""
    prefix: str
    interface: str
    route_type: str  # 'connected' или 'static'
    role: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "prefix": self.prefix,
            "interface": self.interface,
            "route_type": self.route_type,
            "role": self.role,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Route":
        return cls(
            prefix=data["prefix"],
            interface=data["interface"],
            route_type=data["route_type"],
            role=data.get("role", ""),
            description=data.get("description", ""),
        )


@dataclass
class GoldenRIB:
    """Golden RIB для одного узла."""
    node_id: str  # loopback адрес
    node_name: str
    ipv4_routes: List[Route] = field(default_factory=list)
    ipv6_routes: List[Route] = field(default_factory=list)

    def get_ipv4_prefixes(self) -> set:
        """Возвращает множество IPv4 префиксов."""
        return {route.prefix for route in self.ipv4_routes}

    def get_ipv6_prefixes(self) -> set:
        """Возвращает множество IPv6 префиксов."""
        return {route.prefix for route in self.ipv6_routes}

    def get_route_by_prefix(self, prefix: str, af: str = "ipv4") -> Optional[Route]:
        """Находит маршрут по префиксу."""
        routes = self.ipv4_routes if af == "ipv4" else self.ipv6_routes
        for route in routes:
            if route.prefix == prefix:
                return route
        return None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "ipv4_routes": [r.to_dict() for r in self.ipv4_routes],
            "ipv6_routes": [r.to_dict() for r in self.ipv6_routes],
        }


class SoTReader:
    """Читатель данных SoT и генератор Golden RIB."""

    def __init__(self, sot_path: Path):
        self.sot_path = sot_path
        self._data: Optional[dict] = None
        self._golden_ribs: Dict[str, GoldenRIB] = {}

    def load(self) -> None:
        """Загружает данные SoT из файла."""
        logger.info(f"Загрузка SoT из {self.sot_path}")
        with open(self.sot_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        logger.info(f"SoT загружен, schema: {self._data.get('meta', {}).get('schema', 'unknown')}")

    def _build_golden_rib_for_node(self, loopback: str, node_data: dict) -> GoldenRIB:
        """Строит Golden RIB для одного узла."""
        node_info = node_data.get("node", {})
        node_name = node_info.get("name", loopback)

        rib = GoldenRIB(node_id=loopback, node_name=node_name)

        vrfs = node_data.get("vrfs", {})
        default_vrf = vrfs.get("default", {})

        # Обработка IPv4
        ipv4_data = default_vrf.get("ipv4", {})
        self._process_af_data(rib, ipv4_data, "ipv4")

        # Обработка IPv6
        ipv6_data = default_vrf.get("ipv6", {})
        self._process_af_data(rib, ipv6_data, "ipv6")

        # Добавляем loopback как connected маршрут
        loopbacks = node_info.get("loopbacks", {})
        if loopbacks.get("ipv4"):
            rib.ipv4_routes.append(Route(
                prefix=loopbacks["ipv4"],
                interface="Loopback0",
                route_type="connected",
                role="loopback",
                description="Node loopback"
            ))
        if loopbacks.get("ipv6"):
            rib.ipv6_routes.append(Route(
                prefix=loopbacks["ipv6"],
                interface="Loopback0",
                route_type="connected",
                role="loopback",
                description="Node loopback"
            ))

        logger.debug(
            f"Golden RIB для {loopback} ({node_name}): "
            f"{len(rib.ipv4_routes)} IPv4, {len(rib.ipv6_routes)} IPv6 маршрутов"
        )
        return rib

    def _process_af_data(self, rib: GoldenRIB, af_data: dict, af: str) -> None:
        """Обрабатывает данные для одного address family."""
        routes_list = rib.ipv4_routes if af == "ipv4" else rib.ipv6_routes

        # Connected маршруты
        connected = af_data.get("connected_by_interface", {})
        for iface, iface_data in connected.items():
            local_addr = iface_data.get("local_address", "")
            if local_addr:
                routes_list.append(Route(
                    prefix=local_addr,
                    interface=iface,
                    route_type="connected",
                    role="p2p_link",
                    description=f"Connected on {iface}"
                ))

        # Remote (static) маршруты
        remote = af_data.get("remote_by_interface", {})
        for iface, iface_data in remote.items():
            routes_by_prefix = iface_data.get("routes_by_prefix", {})
            for prefix, route_info in routes_by_prefix.items():
                routes_list.append(Route(
                    prefix=prefix,
                    interface=iface,
                    route_type="static",
                    role=route_info.get("role", ""),
                    description=route_info.get("description", "")
                ))

    def build_golden_ribs(self) -> Dict[str, GoldenRIB]:
        """Строит Golden RIB для всех узлов."""
        if self._data is None:
            self.load()

        nodes = self._data.get("nodes_by_loopback", {})
        logger.info(f"Построение Golden RIB для {len(nodes)} узлов")

        for loopback, node_data in nodes.items():
            rib = self._build_golden_rib_for_node(loopback, node_data)
            self._golden_ribs[loopback] = rib

        logger.info(f"Golden RIB построены для всех узлов")
        return self._golden_ribs

    def get_golden_rib(self, node_id: str) -> Optional[GoldenRIB]:
        """Возвращает Golden RIB для узла по его ID (loopback)."""
        if not self._golden_ribs:
            self.build_golden_ribs()
        return self._golden_ribs.get(node_id)

    def get_all_node_ids(self) -> List[str]:
        """Возвращает список всех node_id."""
        if not self._golden_ribs:
            self.build_golden_ribs()
        return list(self._golden_ribs.keys())
