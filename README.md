# IPAM Prototype

Прототип системы управления маршрутизацией для ЦОД на основе Source of Truth (SoT).

## Установка

```bash
pip install -r requirements.txt
```

## Использование

### 1. Запуск агента (эмуляция коммутатора)

```bash
python run_agent.py --node-id 10.255.0.11 --port 50052 --routes-file data/node_routes_leaf01.json
```

### 2. IPAM Server

```bash
# Список узлов
python run_server.py

# Просмотр Golden RIB
python run_server.py --show-rib 10.255.0.11

# Проверка синхронизации (без изменений)
python run_server.py --sync 10.255.0.11

# Применение изменений
python run_server.py --sync-apply 10.255.0.11
```

## Структура

- `data/sot.json` - Source of Truth (целевое состояние сети)
- `data/nodes_config.json` - адреса подключения к агентам
- `src/ipam/golden_rib.py` - формирование Golden RIB из SoT
- `src/ipam/sync.py` - сравнение и генерация инструкций синхронизации
- `src/ipam/node_agent.py` - gRPC сервер агента на узле
- `src/ipam/ipam_server.py` - IPAM сервер

## Логи

Все логи пишутся в `logs/`.
