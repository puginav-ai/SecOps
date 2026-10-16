#!/bin/sh
# SeaweedFS all-in-one (master + volume + filer + S3). S3-креды генерируются из окружения:
# в репозитории секретов нет, значения приходят из .env (S3_ACCESS_KEY / S3_SECRET_KEY).
set -e

cat > /tmp/s3.json <<EOF
{
  "identities": [
    {
      "name": "secops",
      "credentials": [{"accessKey": "${S3_ACCESS_KEY}", "secretKey": "${S3_SECRET_KEY}"}],
      "actions": ["Admin", "Read", "Write"]
    }
  ]
}
EOF

exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json
