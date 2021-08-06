#!/bin/bash
. /u01/oracle/config/domain/ngsbgpp_domain/bin/setDomainEnv.sh
cd /home/sbgpp/wlst/manageOSB
/u01/oracle/products/fmw/12.2.1.3.0/oracle_common/common/bin/wlst.sh manageOSB.py -skipWLSModuleScanning
