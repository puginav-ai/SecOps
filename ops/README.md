# ops/ — эксплуатация

- `compose.yaml` — стек: nginx, web, worker, beat, postgres, redis, s3 (SeaweedFS) (`name: secops`).
  Профиль `scan` (collector) добавляется на неделе 2.
- `entrypoint.sh` — миграции и collectstatic только для web (gunicorn).
- `seaweedfs/entrypoint.sh` — S3-хранилище evidence; креды генерируются из `.env`
  (`S3_ACCESS_KEY` / `S3_SECRET_KEY`), в репозитории секретов нет.
- `nginx/grc.conf` — TLS-терминация, статика, прокси на web.
- `certs/gen-dev-cert.sh` — самоподписанный сертификат для разработки.
  **Прод:** сертификат внутреннего УЦ, положить как `ops/certs/tls.crt` + `tls.key`.
- `backup.sh` — pg_dump (ретенция 30 дней) + снапшот S3 в `backups/`.
  Хранилище на время снапшота (секунды, ночью) останавливается — доказательства недоступны,
  это ожидаемо и укладывается в RPO 24 ч / RTO 4 ч.
- `restore-check.sh` — проверка восстановления БД на временную БД
  (ежемесячно; оформлено обязательством в пульте).
- `systemd/` — таймер ежедневного бэкапа (02:30):
  `cp ops/systemd/* /etc/systemd/system/ && systemctl enable --now grc-backup.timer`

Восстановление S3-хранилища:

```sh
docker compose -f ops/compose.yaml stop s3
docker volume rm secops_s3data && docker volume create secops_s3data
docker run --rm -v secops_s3data:/data -v "$PWD/backups/s3:/src:ro" alpine:3.22 \
    sh -c 'tar -xzf /src/data_ГОД-МЕСЯЦ-ДЕНЬ_ЧЧММ.tar.gz -C /data'
docker compose -f ops/compose.yaml start s3
```

После восстановления — скачать пару доказательств через UI (проверка целостности) и прогнать `restore-check.sh`.

Раскладка на VM: `/opt/grc` = этот репозиторий; `.env` (chmod 600), `certs/`, `backups/` — рядом,
в репозиторий не попадают.
