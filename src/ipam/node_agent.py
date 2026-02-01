"""
Node Agent - gRPC сервис на узле (эмуляция коммутатора).
Слушает порт и отвечает на запросы IPAM сервера.
Данные маршрутов читаются из локального JSON файла.
"""
import json
import logging
import sys
from concurrent import futures
from pathlib import Path
from typing import List, Optional

import grpc

# Добавляем путь к сгенерированным proto файлам
sys.path.insert(0, str(Path(__file__).parent))
from proto_gen import ipam_pb2
from proto_gen import ipam_pb2_grpc

logger = logging.getLogger(__name__)


class NodeAgentServicer(ipam_pb2_grpc.NodeAgentServicer):
    """Реализация gRPC сервиса агента на узле."""

    def __init__(self, node_id: str, routes_file: Path):
        """
        Args:
            node_id: Идентификатор узла (loopback)
            routes_file: Путь к JSON файлу с маршрутами
        """
        self.node_id = node_id
        self.routes_file = routes_file
        self._routes: List[dict] = []
        self._load_routes()

    def _load_routes(self) -> None:
        """Загружает маршруты из файла."""
        if not self.routes_file.exists():
            logger.warning(f"Файл маршрутов не найден: {self.routes_file}")
            self._routes = []
            return

        logger.info(f"Загрузка маршрутов из {self.routes_file}")
        with open(self.routes_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self._routes = data.get("routes", [])
        logger.info(f"Загружено {len(self._routes)} маршрутов")

    def _save_routes(self) -> None:
        """Сохраняет маршруты в файл."""
        logger.info(f"Сохранение маршрутов в {self.routes_file}")
        with open(self.routes_file, "w", encoding="utf-8") as f:
            json.dump({"node_id": self.node_id, "routes": self._routes}, f, indent=2)
        logger.info(f"Сохранено {len(self._routes)} маршрутов")

    def _route_to_proto(self, route: dict) -> ipam_pb2.Route:
        """Конвертирует dict маршрут в proto."""
        af = ipam_pb2.AF_IPV4 if route.get("af", "ipv4") == "ipv4" else ipam_pb2.AF_IPV6
        route_type = (
            ipam_pb2.ROUTE_TYPE_CONNECTED
            if route.get("route_type") == "connected"
            else ipam_pb2.ROUTE_TYPE_STATIC
        )
        return ipam_pb2.Route(
            prefix=route.get("prefix", ""),
            interface=route.get("interface", ""),
            route_type=route_type,
            role=route.get("role", ""),
            description=route.get("description", ""),
            af=af,
        )

    def _proto_to_route(self, proto_route: ipam_pb2.Route) -> dict:
        """Конвертирует proto маршрут в dict."""
        af = "ipv4" if proto_route.af == ipam_pb2.AF_IPV4 else "ipv6"
        route_type = (
            "connected"
            if proto_route.route_type == ipam_pb2.ROUTE_TYPE_CONNECTED
            else "static"
        )
        return {
            "prefix": proto_route.prefix,
            "interface": proto_route.interface,
            "route_type": route_type,
            "role": proto_route.role,
            "description": proto_route.description,
            "af": af,
        }

    def GetRoutes(self, request: ipam_pb2.GetRoutesRequest, context) -> ipam_pb2.GetRoutesResponse:
        """Возвращает текущие маршруты узла."""
        logger.info(f"GetRoutes запрос, af={request.af}")
        self._load_routes()  # Перечитываем файл

        routes = []
        for route in self._routes:
            # Фильтруем по AF если указан
            if request.af == ipam_pb2.AF_IPV4 and route.get("af") == "ipv6":
                continue
            if request.af == ipam_pb2.AF_IPV6 and route.get("af") == "ipv4":
                continue
            routes.append(self._route_to_proto(route))

        logger.info(f"Возвращаем {len(routes)} маршрутов")
        return ipam_pb2.GetRoutesResponse(node_id=self.node_id, routes=routes)

    def ApplyChanges(
        self, request: ipam_pb2.ApplyChangesRequest, context
    ) -> ipam_pb2.ApplyChangesResponse:
        """Применяет изменения к маршрутам."""
        logger.info(f"ApplyChanges запрос, {len(request.instructions)} инструкций")

        results = []
        for instruction in request.instructions:
            route_dict = self._proto_to_route(instruction.route)
            success = True
            error_msg = ""

            try:
                if instruction.action == ipam_pb2.ROUTE_ACTION_ADD:
                    # Проверяем, что маршрут не существует
                    exists = any(r["prefix"] == route_dict["prefix"] for r in self._routes)
                    if exists:
                        error_msg = f"Маршрут {route_dict['prefix']} уже существует"
                        success = False
                        logger.warning(error_msg)
                    else:
                        self._routes.append(route_dict)
                        logger.info(f"Добавлен маршрут: {route_dict['prefix']} via {route_dict['interface']}")

                elif instruction.action == ipam_pb2.ROUTE_ACTION_DELETE:
                    # Ищем и удаляем маршрут
                    found = False
                    for i, r in enumerate(self._routes):
                        if r["prefix"] == route_dict["prefix"]:
                            del self._routes[i]
                            found = True
                            logger.info(f"Удалён маршрут: {route_dict['prefix']}")
                            break
                    if not found:
                        error_msg = f"Маршрут {route_dict['prefix']} не найден"
                        success = False
                        logger.warning(error_msg)

            except Exception as e:
                success = False
                error_msg = str(e)
                logger.error(f"Ошибка при применении изменений: {e}")

            results.append(ipam_pb2.InstructionResult(
                success=success,
                error_message=error_msg,
                route=instruction.route,
            ))

        # Сохраняем изменения
        self._save_routes()

        overall_success = all(r.success for r in results)
        return ipam_pb2.ApplyChangesResponse(success=overall_success, results=results)


def serve(node_id: str, routes_file: Path, port: int = 50051) -> None:
    """Запускает gRPC сервер агента."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = NodeAgentServicer(node_id, routes_file)
    ipam_pb2_grpc.add_NodeAgentServicer_to_server(servicer, server)

    address = f"[::]:{port}"
    server.add_insecure_port(address)

    logger.info(f"Node Agent для {node_id} запускается на порту {port}")
    server.start()
    logger.info(f"Node Agent запущен и слушает на {address}")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
        server.stop(grace=5)
        logger.info("Node Agent остановлен")
