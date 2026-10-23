# Database

## Запуск

**Linux/macOS:**
```bash
./db.sh
```

**Windows:**
```cmd
.\db.cmd
```

## Пересоздание БД (удалит все данные)

**Linux/macOS:**
```bash
./db.sh reset
```

**Windows:**
```cmd
.\db.cmd reset
```

## Строка подключения по умолчанию

Из другого контейнера в той же docker-сети:
```
postgresql://cm_admin:admin_password@db:5432/construction_monitoring
```

С хост-машины:
```
postgresql://cm_admin:admin_password@localhost:54321/construction_monitoring
```
