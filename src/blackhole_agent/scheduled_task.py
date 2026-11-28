"""Windows Task Scheduler XML for the daily hygiene and logon restore commands."""

import subprocess
import sys
from xml.sax.saxutils import escape


def task_xml(registration: dict, default_name: str, trigger: str) -> str:
    command = [str(arg) for arg in registration.get("command") or [sys.executable]]
    name = escape(str(registration.get("name") or default_name))
    arguments = escape(subprocess.list2cmdline(command[1:]))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><URI>\\{name}</URI></RegistrationInfo>
  <Triggers>{trigger}</Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec>
    <Command>{escape(command[0])}</Command>
    <Arguments>{arguments}</Arguments>
  </Exec></Actions>
</Task>
'''
