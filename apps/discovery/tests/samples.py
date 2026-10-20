"""Вымышленные XML-выгрузки nmap для тестов. Реальных сетей и данных здесь нет."""

from __future__ import annotations

# Свип: два живых узла (один с MAC) и один недоступный
SWEEP_XML = """<?xml version="1.0"?><nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.60.1.10" addrtype="ipv4"/>
    <address addr="AA:BB:CC:00:00:01" addrtype="mac" vendor="Demo Vendor"/>
  </host>
  <host>
    <status state="up"/>
    <address addr="10.60.1.11" addrtype="ipv4"/>
  </host>
  <host>
    <status state="down"/>
    <address addr="10.60.1.12" addrtype="ipv4"/>
  </host>
</nmaprun>
"""

# Порт-скан тех же узлов: порты, имя хоста, отпечаток ОС
DETAIL_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.60.1.10" addrtype="ipv4"/>
    <address addr="aa:bb:cc:00:00:01" addrtype="mac"/>
    <hostnames><hostname name="srv-demo"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22"><state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9p1"/></port>
      <port protocol="tcp" portid="80"><state state="closed"/></port>
      <port protocol="tcp" portid="443"><state state="open"/>
        <service name="https" product="nginx" version="1.24.0"/></port>
    </ports>
    <os><osmatch name="Linux 5.4"/></os>
  </host>
  <host>
    <status state="up"/>
    <address addr="10.60.1.11" addrtype="ipv4"/>
    <hostnames><hostname name="pc-demo"/></hostnames>
    <ports><port protocol="tcp" portid="3389"><state state="open"/>
      <service name="ms-wbt-server"/></port></ports>
  </host>
</nmaprun>
"""

# Строки, которые nmap не должен выдавать, но парсер обязан пережить
WEIRD_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.60.1.77" addrtype="ipv4"/>
    <address addr="AA:BB:CC:00:00:77" addrtype="mac"/>
    <ports>
      <port protocol="tcp" portid="tcp"><state state="open"/></port>
      <port protocol="tcp" portid="8080"><state state="closed"/></port>
    </ports>
  </host>
  <host>
    <status state="up"/>
    <address addr="не-ip" addrtype="ipv4"/>
  </host>
  <host>
    <status state="down"/>
    <address addr="10.60.1.78" addrtype="ipv4"/>
  </host>
</nmaprun>
"""

# SMB/RDP-зонд ОС: в тестах скана — пустой ответ (проверяется отдельным парсером)
OS_PROBE_XML = '<?xml version="1.0"?><nmaprun></nmaprun>'
