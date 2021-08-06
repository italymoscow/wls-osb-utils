@echo OFF
title %~nx0

set YYYY-MM-DD=%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%
set HH-mm-ss=%TIME:~0,8%
echo [INFO] %YYYY-MM-DD% %HH-mm-ss% Starting the WLST script....

set PATH=%PATH%;%ORACLE_HOME122%\oracle_common\common\bin
set CLASSPATH=%CLASSPATH%;%ORACLE_HOME%\osb\lib\modules\oracle.servicebus.kernel-api.jar;%ORACLE_HOME%\osb\lib\modules\oracle.servicebus.kernel-wls.jar;%ORACLE_HOME%\osb\lib\modules\oracle.servicebus.configfwk.jar

call WLST manageOSB.py -skipWLSModuleScanning
pause
