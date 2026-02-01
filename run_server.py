#!/usr/bin/env python3
"""
Запуск IPAM Server - серверное приложение для управления маршрутизацией.
Пример: python run_server.py --sot-file data/sot.json --nodes-config data/nodes_config.json
"""
import argparse
import sys
from pathlib import Path

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ipam.logging_config import setup_logging
from ipam.ipam_server import IPAMServer


def main():
    parser = argparse.ArgumentParser(description="IPAM Server")
    parser.add_argument(
        "--sot-file",
        default="data/sot.json",
        help="Путь к файлу SoT (по умолчанию data/sot.json)"
    )
    parser.add_argument(
        "--nodes-config",
        default="data/nodes_config.json",
        help="Путь к конфигурации узлов (по умолчанию data/nodes_config.json)"
    )
    parser.add_argument(
        "--log-level",
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Уровень логирования"
    )
    parser.add_argument(
        "--show-rib",
        metavar="NODE_ID",
        help="Показать Golden RIB для указанного узла и выйти"
    )
    parser.add_argument(
        "--sync",
        metavar="NODE_ID",
        help="Синхронизировать указанный узел (только проверка, без изменений)"
    )
    parser.add_argument(
        "--sync-apply",
        metavar="NODE_ID",
        help="Синхронизировать указанный узел с применением изменений"
    )
    parser.add_argument(
        "--sync-all",
        action="store_true",
        help="Синхронизировать все узлы (только проверка)"
    )
    parser.add_argument(
        "--sync-all-apply",
        action="store_true",
        help="Синхронизировать все узлы с применением изменений"
    )

    args = parser.parse_args()

    # Настраиваем логирование
    import logging
    log_level = getattr(logging, args.log_level)
    setup_logging(log_level=log_level, app_name="ipam_server")

    # Резолвим пути
    project_root = Path(__file__).parent
    sot_path = Path(args.sot_file)
    if not sot_path.is_absolute():
        sot_path = project_root / sot_path

    nodes_config_path = Path(args.nodes_config)
    if not nodes_config_path.is_absolute():
        nodes_config_path = project_root / nodes_config_path

    # Создаём и загружаем сервер
    server = IPAMServer(sot_path, nodes_config_path)
    server.load()

    # Выполняем команду
    if args.show_rib:
        server.print_golden_rib(args.show_rib)
        return

    if args.sync:
        results = server.sync_node(args.sync, apply_changes=False)
        if results:
            print_sync_results(args.sync, results)
        return

    if args.sync_apply:
        results = server.sync_node(args.sync_apply, apply_changes=True)
        if results:
            print_sync_results(args.sync_apply, results)
        return

    if args.sync_all:
        all_results = server.sync_all_nodes(apply_changes=False)
        for node_id, results in all_results.items():
            print_sync_results(node_id, results)
        return

    if args.sync_all_apply:
        all_results = server.sync_all_nodes(apply_changes=True)
        for node_id, results in all_results.items():
            print_sync_results(node_id, results)
        return

    # Если нет команды - показываем все Golden RIB
    print("Доступные узлы:")
    for node_id in server.get_all_node_ids():
        rib = server.get_golden_rib(node_id)
        print(f"  {node_id} ({rib.node_name}): {len(rib.ipv4_routes)} IPv4, {len(rib.ipv6_routes)} IPv6 маршрутов")

    print("\nИспользуйте --show-rib NODE_ID для просмотра Golden RIB")
    print("Используйте --sync NODE_ID для проверки синхронизации")
    print("Используйте --sync-apply NODE_ID для применения изменений")


def print_sync_results(node_id: str, results: dict):
    """Выводит результаты синхронизации."""
    print(f"\n=== Результаты синхронизации для {node_id} ===")

    for af, result in results.items():
        status = "IN SYNC" if result.in_sync else "OUT OF SYNC"
        print(f"\n{af.upper()}: {status}")

        if result.missing_routes:
            print(f"  Отсутствующие маршруты (нужно добавить):")
            for route in result.missing_routes:
                print(f"    + {route.prefix} via {route.interface}")

        if result.extra_routes:
            print(f"  Лишние маршруты (нужно удалить):")
            for route in result.extra_routes:
                print(f"    - {route.prefix} via {route.interface}")

        if result.in_sync:
            print(f"  Все маршруты в синхронизации")


if __name__ == "__main__":
    main()
