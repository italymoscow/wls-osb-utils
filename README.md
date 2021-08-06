# wls-osb-utils
The script contains a set of utilities for managing OSB projects.

## Functinality
Currently the script has the following functionality:
    
    [0] Change connection to a different environment (without leaving the WLST script)
    [1] List projects deployed on server
    [2] List proxy services deployed on server (Project, full path, uri and work manager)
    [3] List business services deployed on server (Project, full path, uri and work manager)
    [4] Undeploy OSB projects (if required, incl. its work managers and JMS queues)
    [5] Get project details (Full path, uri, work managers)
    [6] Discard open OSB sessions (NB! Not yet supported)
    [7] Disable/Enable proxy services (Input: one or several proxy service full paths, e.g. prj1/fldr1/prxy1 p2/f2/px2)
    [8] Disable/Enable proxy service monitoring (same as for [7])

## Manual usage:
1. Source domain variables, e.g (. /u02/private/oracle/config/domains/osbdomain/bin/setDomainEnv.sh)
2. Execute: wlst manageOSB.py
3. Select environment from the provided list of values (see the description of get_env_prop_file)
4. Select action [0 - 8]. See the list of actions above.

Standalone usage: see the description of the required function
