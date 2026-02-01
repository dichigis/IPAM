#!/usr/bin/env python3
"""
Запуск Node Agent - эмуляция коммутатора.
Пример: python run_agent.py --node-id 10.255.0.11 --port 50052 --routes-file data/node_routes_leaf01.json
"""
import argparse
import sys
from pathlib import Path

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ipam.logging_config import setup_logging
from ipam.node_agent import serve


def main():
    parser = argparse.ArgumentParser(description="IPAM Node Agent")
    parser.add_argument(
        "--node-id",
        required=True,
        help="Идентификатор узла (loopback адрес)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=50051,
        help="Порт для gRPC сервера (по умолчанию 50051)"
    )
    parser.add_argument(
        "--routes-file",
        required=True,
        help="Путь к JSON файлу с маршрутами"
    )
    parser.add_argument(
        "--log-level",
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Уровень логирования"
    )

    args = parser.parse_args()

    # Настраиваем логирование
    import logging
    log_level = getattr(logging, args.log_level)
    setup_logging(
        log_level=log_level,
        app_name=f"node_agent_{args.node_id.replace('.', '_')}"
    )

    routes_file = Path(args.routes_file)
    if not routes_file.is_absolute():
        routes_file = Path(__file__).parent / routes_file

    print(f"Запуск Node Agent для {args.node_id} на порту {args.port}")
    print(f"Файл маршрутов: {routes_file}")
    print("Нажмите Ctrl+C для остановки")

    serve(args.node_id, routes_file, args.port)


if __name__ == "__main__":
    main()
