
"""
The script contains a set of utilities for managing OSB projects.

Currently the script has the following functionality:
    [0] Change connection to a different environment
    [1] List projects deployed on server
    [2] List proxy services deployed on server (Project, full path, uri and work manager)
    [3] List business services deployed on server (Project, full path, uri and work manager)
    [4] Undeploy OSB projects (if required, incl. its work managers and JMS queues)
    [5] Get project details (Full path, uri, work manager)
    [6] Discard open OSB sessions (NB! Not yet supported)
    [7] Disable/Enable proxy services (Input: one or several proxy service full paths, e.g. prj1/fldr1/prxy1 p2/f2/px2)
    [8] Disable/Enable proxy service monitoring (same as for [7])

Manual usage:
1. Source domain variables, e.g (. /u02/private/oracle/config/domains/osbdomain/bin/setDomainEnv.sh)
2. Execute: wlst manageOSB.py
3. Select environment from the provided list of values (see the description of get_env_prop_file)
4. Select action [0 - 7]. See the list of actions above

Standalone usage: see the description of the required function
"""

import os
import os.path
import sys
import random

from time import strftime, localtime

from java.util import Collections
from java.util import Properties

from java.io import File
from java.io import FileInputStream

from xml.dom.minidom import parseString
from com.bea.wli.sb.util import EnvValueTypes
from com.bea.wli.sb.util import Refs
from com.bea.wli.config import Ref
from com.bea.wli.config.mbeans import SessionMBean
from com.bea.wli.sb.management.configuration import SessionManagementMBean
from com.bea.wli.sb.management.configuration import ALSBConfigurationMBean
from com.bea.wli.sb.management.configuration import CommonServiceConfigurationMBean
from com.bea.wli.sb.management.configuration import ProxyServiceConfigurationMBean
from com.bea.wli.sb.management.configuration import BusinessServiceConfigurationMBean
from com.bea.wli.sb.management.query import ProxyServiceQuery
from com.bea.wli.sb.management.query import BusinessServiceQuery
from com.bea.wli.config.resource import ResourceQuery


def undeploy_osb_prj(connection_info):
    """
    This function undeploys the given projects and deletes by prompt WLS queues and Work Managers used by them.
    Input: Space separated list of OSB projects.
    Output: Tabular report of the objects with status: deleted, skipped or failed.
    Automatic usage:
        wlst manageOSB.py undeploy_osb_prj [env] [project names]
    """
    prj_names = []
    
    if is_standalone:
        print(str(len(sys.argv)))
        print(str(sys.argv))
        print(str(sys.argv[3:]))
        if len(sys.argv) >= 4:
            prj_names = " ".join(sys.argv[3:])
    else:
        prj_names = raw_input("[INPUT] Enter one or several project names separated by space: ").strip()
    
    if not prj_names:
        if is_standalone:
            raise ValueError("List of project names must contain at least one name.")
        else:
            log("ERROR", "List of project names must contain at least one name.")
            return

    prj_names = prj_names.split(" ")

    log("INFO", "Projects to delete: " + ", ".join(prj_names) + ".")
    report = []
    report_title = "REPORT: Delete OSB projects from '" + connection_info["url"] + "'"
    column_names = ("OBJECT_TYPE", "OBJECT_NAME", "STATUS")

    for prj_name in prj_names:
        if not prj_name:
            continue
        prj_name = prj_name.strip()
        print("")
        print("=========================================================")
        log("INFO", "Processing project '" + prj_name + "'...")

        # Get a report on the project [Business/Proxy, URI, Work manager]
        try:
            prj_details_report = get_prj_details(prj_name)
        except:
            log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
            log("ERROR", "Error when getting project details for '" + prj_name + "'. Try to reconnect")
            return
        
        if prj_details_report == "Not found":
            log("WARNING", "OSB project '" + prj_name + "' could not be found on '" + connection_info["url"] + "'.")
            print("")
            report.append(["OSB project", prj_name, "Not found"])
            continue
        elif prj_details_report == "Project is empty":
            log("WARNING", "OSB project '" + prj_name + "' was found on '" + connection_info["url"] + "', but is empty.")
            print("")
            report.append(["OSB project", prj_name, "Project is empty"])
        else:
            prj_details_report_title = "REPORT: Project details for '" + prj_name + "' on '" + connection_info["url"] + "'"
            prj_details_column_names = ("SERVICE_PATH", "ENBLD#", "URI", "WORK_MANAGER")
            create_report(prj_details_report_title, prj_details_report, prj_details_column_names, is_sorted=True)

        session_name = connection_info["username"] + "_" + str(System.currentTimeMillis())

        try:
            log("INFO", "Creating session '" + session_name + "'...")
            session_mbean = findService(SessionManagementMBean.NAME, SessionManagementMBean.TYPE)
            session_mbean.createSession(session_name)
            log("INFO", "Created session '" + session_name + "'.")
            prj_ref = Ref(Ref.PROJECT_REF, Ref.DOMAIN, prj_name)
            alsb_mbean = findService("ALSBConfiguration." + str(session_name),
                                     "com.bea.wli.sb.management.configuration.ALSBConfigurationMBean")
            
            if alsb_mbean.exists(prj_ref):
                if is_standalone:
                    del_prj_choice = "Y"
                else:
                    del_prj_choice = raw_input("[INPUT] Do you really want to delete project '" + prj_name + "', Y/N [Y]? ")
                
                if del_prj_choice.upper() == "Y" or del_prj_choice.strip() == "":
                    log("INFO", "Deleting OSB project '" + prj_name + "'...")
                    alsb_mbean.delete(Collections.singleton(prj_ref))
                    log("INFO", "Project '" + prj_name + "' deleted. Activating session '" + session_name + "'...")
                    session_mbean.activateSession(session_name, "Deleted '" + prj_name + "'")
                    report.append(["OSB project", prj_name, "Deleted"])
                    print("")
                else:
                    log("INFO", "OSB project '" + prj_name + "' was skipped by user")
                    report.append(["OSB project", prj_name, "Skipped by user"])
                    continue
            else:
                log("WARNING", "OSB project '" + prj_name + "' could not be found on '" + connection_info["url"] + "'.")
                print("")
                report.append(["OSB project", prj_name, "Not found"])
                continue  # to the next prj_name

        except:
            report.append(["OSB project", prj_name, "Failed"])
            log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
            log("WARNING", "Error when deleting project '" + prj_name + "'. Discarding session '" + session_name + "'...")
            discard_session(session_mbean, session_name)
            print("")
            # create_report(report_title, report, column_names, is_sorted=True)
            # print("")
            continue # to the next project

        # Check report for Work Managers and JMS Queues
        # JMS queues (only unique names)
        if prj_details_report and type(prj_details_report) is list:
            try:
                jms_queues = []
                for row in prj_details_report:
                    jms_uri = str(row[2])  # row[2] represents uri in the array of row
                    if jms_uri and "jms://" in jms_uri:
                        # get queue name from jms_uri
                        jms_uri = jms_uri.split("/")
                        qjndi = jms_uri[-1]
                        queue_name = qjndi.split(".")[-1]
                        jms_queues.append(queue_name)
                
                # Leave only unique names
                jms_queues_unique = []  # Just another workaround as set() is not available
                for queue_name in jms_queues:
                    if queue_name not in jms_queues_unique:
                        jms_queues_unique.append(queue_name)
                
                for queue_name in jms_queues_unique:
                    log("INFO", "The project was using queue '" + queue_name + "'.")
                    print("")
                    queues_report = delete_queue(queue_name)
                    if queues_report:
                        for row in queues_report:
                            report.append(row)

            except:
                log("ERROR", "Error while processing JMS queues")
                log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
                # log("INFO", "Script execution report:")
                # create_report(report_title, report, column_names, is_sorted=True)
                # print("")

            # Work managers (only unique names)
            try:
                wm_names = []
                for row in prj_details_report:
                    wm_name = str(row[3])  # Represents Work manager in the array of row
                    if wm_name and wm_name not in("SBDefaultResponseWorkManager", "None", "default"):
                        wm_names.append(wm_name)
                
                # Leave only unique names
                wm_names_unique = []  # Just another workaround as set() is not available
                for wm_name in wm_names:
                    if wm_name not in wm_names_unique:
                        wm_names_unique.append(wm_name)
                
                for wm_name in wm_names_unique:
                    print("")
                    
                    if is_standalone:
                        del_wm_choice = "Y"
                    else:
                        del_wm_choice = raw_input("[INPUT] The project was using Work Manager '"
                                            + wm_name + "'. Delete it, Y/N [Y]? ")
                    
                    if del_wm_choice.upper() == "Y" or del_wm_choice.strip() == "":
                        log("INFO", "Processing work manager '" + wm_name + "'...")
                        wm_report = delete_work_manager(wm_name)
                        if wm_report:
                            for row in wm_report:
                                report.append(row)
                    else:
                        log("INFO", "Deleting Work manager '" + wm_name + "' was skipped by the user.")
                        report.append(["Work manager", wm_name, "Skipped"])

            except:
                log("ERROR", "Error while processing Work Managers")
                log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
                report.append(["Work manager", wm_name, "Failed"])
                # log("INFO", "Script execution report:")
                # create_report(report_title, report, column_names, is_sorted=True)
                # print("")

    print("")
    create_report(report_title, report, column_names, is_sorted=True)


def get_prj_details(prj_name):
    """
    This function searches the project by its name.
    Input: A project name by user prompt.
    Output: A tabular report with a list of proxy and business services and their URLs and work managers.
    Automatic usage:
        wlst manageOSB.py get_prj_details [env] [prj_name]
    """
    if not prj_name:
        prj_name = raw_input("[INPUT] Enter a project name: ")
        prj_name = prj_name.strip()
        if not prj_name:
            raise ValueError("Project name cannot be empty.")

    prj_details_report = []
    log("INFO", "Looking for project '" + prj_name + "'...")

    try:
        domainRuntime()
        alsb_mbean = findService(ALSBConfigurationMBean.NAME, ALSBConfigurationMBean.TYPE)
        psc_mbean = findService(ProxyServiceConfigurationMBean.NAME, ProxyServiceConfigurationMBean.TYPE)
        biz_mbean = findService(BusinessServiceConfigurationMBean.NAME, BusinessServiceConfigurationMBean.TYPE)
        ref = Ref("Project", Ref.DOMAIN, prj_name)
        
        if not alsb_mbean.exists(ref):
            return "Not found"
        
        prj_refs = alsb_mbean.getRefs(ref)
        for prj_ref in prj_refs:
            type_id = prj_ref.getTypeId()
            if type_id == "ProxyService":
                prx_full_name = prj_ref.fullName
                service_uri = alsb_mbean.getEnvValue(prj_ref, EnvValueTypes.SERVICE_URI, None)
                wm_name = alsb_mbean.getEnvValue(prj_ref, EnvValueTypes.WORK_MANAGER, None)
                status = psc_mbean.isEnabled(prj_ref)
                prj_details_report.append([prx_full_name, status, service_uri, wm_name])
            elif type_id == "BusinessService":
                biz_full_name = prj_ref.fullName
                service_uri_table = alsb_mbean.getEnvValue(prj_ref, EnvValueTypes.SERVICE_URI_TABLE, None)
                service_url_xml = parseString(service_uri_table.toString())
                xml_uri = service_url_xml.getElementsByTagName("tran:URI")[0].toxml()
                service_uri = xml_uri.replace("<tran:URI>", "").replace("</tran:URI>", "")
                wm_name = alsb_mbean.getEnvValue(prj_ref, EnvValueTypes.WORK_MANAGER, None)
                status = biz_mbean.isEnabled(prj_ref)
                prj_details_report.append([biz_full_name, status, service_uri, wm_name])

        if prj_details_report:
            return prj_details_report
        else:
            return "Empty"

    except:
        log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
        return prj_details_report


def manage_proxy_services(connection_info):
    """
    Function manage_proxy_services activate or deactivates given proxy services depending on user's choice of action:
        1 - activate;
        0 - deactivate.
    Input: Space separated list of services' full names, e.g. Prj1/Proxy/Proxy1 Prj2/Proxy/Proxy2
    Output: Tabular report that contains SERVICE_PATH, STATUS and SERVICE_URI
    """
    while True:
        prx_full_names = raw_input("[INPUT] Enter full paths of proxy services separated by space: ")
        if not prx_full_names:
            print(
                cur_dt() + " [ERROR] The list cannot be empty and must contain at least one path")
            continue

        else:
            break
    prx_full_names = prx_full_names.split(" ")


    action = raw_input("[INPUT] Type '0' to disable or '1' to enable proxy service(-s): ")
    action = int(action.strip())

    if action == 1:
        actionTxt = "enable"
    else:
        actionTxt = "disable"

    log("INFO", "List of projects to be " + actionTxt + "d: " + ", ".join(prx_full_names) + ".")
    
    report = []
    column_names = ("SERVICE_FULL_NAME", "STATUS", "SERVICE_URI")
    report_title = "REPORT: Proxy services " + actionTxt + "d on '" + connection_info["url"] + "'"

    try:
        domainRuntime()
        session_name = connection_info["username"] + "_" + str(System.currentTimeMillis())
        session_mbean = findService(SessionManagementMBean.NAME, SessionManagementMBean.TYPE)
        
        log("INFO", "Creating session '" + session_name + "'...")
        session_mbean.createSession(session_name)
        # log("INFO", "Session '" + session_name + "' created.")
        
        alsb_mbean = findService("ALSBConfiguration." + session_name, ALSBConfigurationMBean.TYPE)
        psc_mbean = findService("ProxyServiceConfiguration." + session_name, ProxyServiceConfigurationMBean.TYPE)
        
        mod_prx_cnt = 0
        prx_full_names_cnt = 0
        
        for prx_full_name in prx_full_names:
            log("INFO", "Processing '" + prx_full_name + "'...")
            prx_full_name = prx_full_name.strip()
            prx_local_name = prx_full_name.split("/")[-1]
            prx_path = "/".join(prx_full_name.split("/")[0:-1])

            query = ProxyServiceQuery()
            query.setLocalName(prx_local_name)
            query.setPath(prx_path)

            prx_refs = alsb_mbean.getRefs(query)

            if prx_refs.size() == 0:
                log("WARNING", "Proxy '" + prx_full_name + "' was not found.")
                report.append([prx_full_name, "Not found", "N/A"])
                continue
            
            prx_full_names_cnt = len(prx_full_names)
            
            for ref in prx_refs:
                service_uri = alsb_mbean.getEnvValue(ref, EnvValueTypes.SERVICE_URI, None)
                is_enabled = psc_mbean.isEnabled(ref)
                
                if action == is_enabled:
                    log("INFO", "Proxy '" + prx_local_name + "' is already " + actionTxt + "d.")
                    report.append([prx_full_name, actionTxt.capitalize() + "d*", service_uri])
                    continue
                
                log("INFO", "Going to " + actionTxt + " '" + prx_local_name + "'...")
                
                if action == 0:
                    psc_mbean.disableService(ref)
                else:
                    psc_mbean.enableService(ref)
                
                mod_prx_cnt += 1

                log("INFO", "Proxy '" + prx_local_name + "' was " + actionTxt + "d successfully.")
                print("")
                
                if prx_full_names_cnt == 1:
                    log("INFO", "Activating session '" + session_name + "'...")
                    if is_standalone:
                        session_mbean.activateSession(session_name, prx_local_name + " " + actionTxt + "d")
                    else:
                        comment = raw_input(
                            "[INPUT] Enter session activation comment: ")
                        session_mbean.activateSession(session_name, comment)
                report.append([prx_full_name, actionTxt.capitalize() + "d", service_uri])

        if prx_full_names_cnt > 1 and mod_prx_cnt > 0:
            log("INFO", "Activating session '" + session_name + "'...")
            if is_standalone:
                session_mbean.activateSession(session_name, str(mod_prx_cnt) + " proxy services " + actionTxt + "d")
            else:
                comment = raw_input(
                    "[INPUT] Enter session activation comment: ")
                session_mbean.activateSession(session_name, comment)
        elif mod_prx_cnt == 0:
            log("INFO", "No proxy services were modified. Discarding session '" + session_name + "'...")
            discard_session(session_mbean, session_name)

        # Create execution report
        print("")
        create_report(report_title, report, column_names, is_sorted=True)

    except (WLSTException, ValueError, NameError, Exception, AttributeError, EOFError), e:
        log("ERROR", "An error occurred in manage_proxy_services. Discarding session...")
        discard_session(session_mbean, session_name)
        if report:
            create_report(report_title, report, column_names, is_sorted=True)
        log("ERROR", str(e))


def proxy_services_monitoring(connection_info):
    """
    proxy_services_monitoring activates or deactivates monitoring of the given proxy services based on the user's choice of action:
        1 - activate;
        0 - deactivate.
    Input: Space separated list of proxy services' full names, e.g. Prj1/Proxy/Proxy1 Prj2/Proxy/Proxy2
    Output: Tabular report that contains SERVICE_PATH, STATUS and SERVICE_URI
    """
    while True:
        prx_full_names = raw_input("[INPUT] Enter full paths of proxy services separated by space: ")
        if not prx_full_names:
            print(
                cur_dt() + " [ERROR] The list cannot be empty and must contain at least one path")
            continue

        else:
            break
    prx_full_names = prx_full_names.strip().split(" ")

    action = raw_input("[INPUT] Type '0' to disable or '1' to enable monitoring of proxy service(-s): ")
    action = int(action.strip())

    if action == 1:
        actionTxt = "enable"
    else:
        actionTxt = "disable"

    log("INFO", "List of proxy service for which monitoring will be " + actionTxt + "d: " + ", ".join(prx_full_names) + ".")
    
    report = []
    column_names = ("SERVICE_FULL_NAME", "MONITORING", "SERVICE_URI")
    report_title = "REPORT: Proxy services for which monitoring has been " + actionTxt + "d on '" + connection_info["url"] + "'"

    try:
        domainRuntime()
        session_name = connection_info["username"] + "_" + str(System.currentTimeMillis())
        session_mbean = findService(SessionManagementMBean.NAME, SessionManagementMBean.TYPE)
        
        log("INFO", "Creating session '" + session_name + "'...")
        session_mbean.createSession(session_name)
        log("INFO", "Session '" + session_name + "' created.")
        
        alsb_mbean = findService("ALSBConfiguration." + session_name, ALSBConfigurationMBean.TYPE)
        psc_mbean = findService("ProxyServiceConfiguration." + session_name, ProxyServiceConfigurationMBean.TYPE)
        
        mod_prx_cnt = 0
        prx_full_names_cnt = 0
        
        for prx_full_name in prx_full_names:
            log("INFO", "Processing '" + prx_full_name + "'...")
            prx_full_name = prx_full_name.strip()
            prx_local_name = prx_full_name.split("/")[-1]
            prx_path = "/".join(prx_full_name.split("/")[0:-1])

            query = ProxyServiceQuery()
            query.setLocalName(prx_local_name)
            query.setPath(prx_path)

            prx_refs = alsb_mbean.getRefs(query)

            if prx_refs.size() == 0:
                log("WARNING", "Proxy '" + prx_full_name + "' was not found.")
                report.append([prx_full_name, "Not found", "N/A"])
                continue
            
            prx_full_names_cnt = len(prx_full_names)
            
            for ref in prx_refs:
                service_uri = alsb_mbean.getEnvValue(ref, EnvValueTypes.SERVICE_URI, None)
                is_enabled = psc_mbean.isMonitoringEnabled(ref)
                
                if action == is_enabled:
                    log("INFO", "Monitoring of proxy '" + prx_local_name + "' is already " + actionTxt + "d.")
                    report.append([prx_full_name, actionTxt.capitalize() + "d*", service_uri])
                    continue
                
                log("INFO", "Going to " + actionTxt + " monitoring of '" + prx_local_name + "'...")
                
                if action == 0:
                    psc_mbean.disableMonitoring(ref)
                else:
                    psc_mbean.enableMonitoring(ref)
                
                mod_prx_cnt += 1

                log("INFO", "Monitoring of proxy '" + prx_local_name + "' was " + actionTxt + "d successfully.")
                print("")
                
                if prx_full_names_cnt == 1:
                    log("INFO", "Activating session '" + session_name + "'...")
                    if is_standalone:
                        session_mbean.activateSession(session_name, prx_local_name + " " + actionTxt + "d")
                    else:
                        comment = raw_input(
                            "[INPUT] Enter session activation comment: ")
                        session_mbean.activateSession(session_name, comment)
                report.append([prx_full_name, actionTxt.capitalize() + "d", service_uri])

        if prx_full_names_cnt > 1 and mod_prx_cnt > 0:
            log("INFO", "Activating session '" + session_name + "'...")
            if is_standalone:
                session_mbean.activateSession(session_name, "Monitoring of " + str(mod_prx_cnt) + " proxy services is" + actionTxt + "d")
            else:
                comment = raw_input(
                    "[INPUT] Enter session activation comment: ")
                session_mbean.activateSession(session_name, comment)
        elif mod_prx_cnt == 0:
            log("INFO", "No proxy services were modified. Discarding session '" + session_name + "'...")
            discard_session(session_mbean, session_name)

        # Create execution report
        print("")
        create_report(report_title, report, column_names, is_sorted=True)

    except (WLSTException, ValueError, NameError, Exception, AttributeError, EOFError), e:
        log("ERROR", "An error occurred in manage_proxy_services. Discarding session...")
        discard_session(session_mbean, session_name)
        if report:
            create_report(report_title, report, column_names, is_sorted=True)
        log("ERROR", str(e))


def discard_session(session_mbean, session_name):
    """
    Function discard_session discards a given sessions
    Input: session_mbean and session_name
    """
    if session_mbean:
        if session_mbean.sessionExists(session_name):
            session_mbean.discardSession(session_name)
            log("INFO", "Session '" + session_name + "' was discarded successfully.")


def discard_sessions():  # Under construction...
    """
    Function discard_sessions discards open OSB sessions, either all or by the given name(-s).
    Input: session_mbean and session_name
    """
    try:
        connect(usrname, password, url)
        domainRuntime()
        session_mbean = findService(SessionMBean.NAME, SessionMBean.TYPE)
        session_names = session_mbean.Sessions
        print("[INFO] Open sessions:")
        for session_name in session_names:
            print(str(session_name))
        print("[1] Discard all open sessions")
        print("[2] Discard specific sessions")
        print("[3] Exit\n\n")
        disc_sessions_choice = raw_input("[INPUT] Select what you want to do: ")
        if disc_sessions_choice == 1:
            for session_name in session_names:
                print("[INFO] Discarding session '" + str(session_name) + "'...")
                discard_session(session_mbean, session_name)
                print("[INFO] Session '" + str(session_name) + "' was discarded successfully.")
        elif disc_sessions_choice == 2:
            spec_sessions = raw_input("[INPUT] Enter session names separated with a space: ")
            spec_sessions_list = spec_sessions.split(" ")
            for session_name in spec_sessions_list:
                print("[INFO] Discarding session '" + str(session_name) + "'...")
                discard_session(session_mbean, session_name)
                print("[INFO] Session '" + str(session_name) + "' was discarded successfully.")
        else:
            return

    except (WLSTException, ValueError, NameError, Exception, AttributeError, EOFError), e:
        print("[ERROR] Error in discard_sessions. ", str(e))


def list_projects(connection_info):
    """
    Function list_projects prints a list of SB projects currently deployed on the given server.
    Automatic usage:
        wlst manageOSB.py list_projects [env]
    """

    report_title = "REPORT: Oracle Service Bus projects deployed on '" + connection_info["url"] + "'"
    column_names = ["PROJECT_NAME"]
    projects = []

    try:
        domainRuntime()
        alsb_mbean = findService(ALSBConfigurationMBean.NAME, ALSBConfigurationMBean.TYPE)
        # As ALSBConfigurationMBean lacks attribute "projects" in 11g, use a workaround.
        # projects = alsb_mbean.projects
        refs_all = alsb_mbean.getRefs(Ref.DOMAIN)

        for ref in refs_all:
            type_id = ref.getTypeId()
            if type_id == Ref.PROJECT_REF:
                prj_name = ref.projectName
                projects.append([prj_name])

        create_report(report_title, projects, column_names, is_sorted=True)

        log("INFO", "Projects count: " + str(len(projects)))
        print("")

    except:
        log("ERROR", "Error while listing  projects. " + str(e))


def list_proxy_services(connection_info):
    """
    Function list_proxy_services prints a  report containing all the proxy services deployed on the given server.
    The report includes project name, proxy service name, proxy status (1 - enabled, 0 - disabled) and
    the service uri of the proxy
    """
    report = []
    report_title = "REPORT: Proxy services deployed on '" + connection_info["url"] + "'"
    column_names = ("PROXY_SERVICE_FULL_NAME", "ENBLD#", "SERVICE_URI")

    try:
        domainRuntime()
        alsb_mbean = findService(ALSBConfigurationMBean.NAME, ALSBConfigurationMBean.TYPE)
        psc_mbean = findService(ProxyServiceConfigurationMBean.NAME, ProxyServiceConfigurationMBean.TYPE)
        
        # refs_all = alsb_mbean.getRefs(Ref.DOMAIN)
        query = ResourceQuery('ProxyService')
        prx_refs = alsb_mbean.getRefs(query)
        
        log("INFO", "Preparing report on proxy services deployed on '" + connection_info["url"] + "'...")

        for ref in prx_refs:
            prx_full_name = ref.fullName
            service_uri = alsb_mbean.getEnvValue(ref, EnvValueTypes.SERVICE_URI, None)
            # workManager = alsb_mbean.getEnvValue(ref, EnvValueTypes.WORK_MANAGER, None)
            status = psc_mbean.isEnabled(ref)
            report.append([prx_full_name, status, service_uri])

        print("")
        create_report(report_title, report, column_names, is_sorted=True)
        log("INFO", "Proxy services count: " + str(prx_refs.size()))
        print("")

    except (WLSTException, ValueError, NameError, Exception, AttributeError, EOFError), e:
        log("ERROR", str(e))
        log("ERROR", "Error while listing Proxy services")


def list_business_services(connection_info):
    """
    Function list_business_services returns  report containing all the business services deployed on the given server.
    The report includes project name, business service name, business service status (1 - enabled, 0 - disabled)
    and a service uri of the business service
    """
    report = []
    report_title = "REPORT: Business services deployed on '" + connection_info["url"] + "'"
    column_names = ("BUSINESS_SERVICE_FULL_NAME", "ENBLD#", "SERVICE_URI")
    log("INFO", "Preparing report on business services deployed on '" + connection_info["url"] + "'...")
    
    try:
        domainRuntime()
        alsb_mbean = findService(ALSBConfigurationMBean.NAME, ALSBConfigurationMBean.TYPE)
        biz_mbean = findService(BusinessServiceConfigurationMBean.NAME, BusinessServiceConfigurationMBean.TYPE)
        
        query = ResourceQuery('BusinessService')
        biz_refs = alsb_mbean.getRefs(query)
        
        for ref in biz_refs:
            biz_full_name = ref.fullName
            service_uri_table = alsb_mbean.getEnvValue(ref, EnvValueTypes.SERVICE_URI_TABLE, None)
            service_url_xml = parseString(service_uri_table.toString())
            xml_uri = service_url_xml.getElementsByTagName('tran:URI')[0].toxml()
            service_uri = xml_uri.replace("<tran:URI>", "").replace("</tran:URI>", "")
            # workManager = alsb_mbean.getEnvValue(ref, EnvValueTypes.WORK_MANAGER, None) - Not used
            status = biz_mbean.isEnabled(ref)
            report.append([biz_full_name, status, service_uri])

        print("")
        create_report(report_title, report, column_names, is_sorted=True)
        log("INFO", "Business services count: " + str(biz_refs.size()))
        print("")

    except (WLSTException, ValueError, NameError, Exception, AttributeError, EOFError), e:
        log("ERROR", str(e))
        log("ERROR", "Error while listing Business Services" + str(sys.exc_info()[0]))


def delete_work_manager(wm_name):
    """
    Function delete_work_manager deletes a given work manager and its min and max threads constraints
    Input: Work manager name
    """
    wm_report = []
    try:
        edit()
        startEdit()
        print("")
        cd('edit:/SelfTuning/')
        domain_name = cmo.name
        cd('/SelfTuning/' + domain_name + '/WorkManagers')
        wm_bean = getMBean(wm_name)
        
        if wm_bean:
            log("INFO", "Work manager '" + wm_name + "' was found.")
            maxtc = wm_bean.getMaxThreadsConstraint()
            mintc = wm_bean.getMinThreadsConstraint()
            
            # First remove MaxThreadsConstraint if exists
            if maxtc:
                maxtc_name = maxtc.name
                log("INFO", "Deleting MaxThreadsConstraint '" + maxtc_name + "'...")
                editService.getConfigurationManager().removeReferencesToBean(maxtc)
                cmo.destroyMaxThreadsConstraint(maxtc)
                log("INFO", "MaxThreadsConstraint '" + maxtc_name + "' was deleted successfully.")
                wm_report.append(["MaxThreadsConstraint", maxtc_name, "Deleted"])
            
            # Then remove MinThreadsConstraint if exists
            if mintc:
                mintc_name = mintc.name
                log("INFO", "Deleting MinThreadsConstraint '" + mintc_name + "'...")
                editService.getConfigurationManager().removeReferencesToBean(mintc)
                cmo.destroyMinThreadsConstraint(mintc)
                log("INFO", "MinThreadsConstraint '" + mintc_name + "' was deleted successfully.")
                wm_report.append(["MinThreadsConstraint", mintc_name, "Deleted"])
            
            # Lastly remove work manager
            log("INFO", "Deleting Work manager '" + wm_name + "'...")
            editService.getConfigurationManager().removeReferencesToBean(wm_bean)
            cmo.destroyWorkManager(wm_bean)
            log("INFO", "Work manager '" + wm_name + "' was deleted successfully.")
            wm_report.append(["Work manager", wm_name, "Deleted"])
            log("INFO", "Saving changes...")
            save()
            log("INFO", "Activating changes...")
            activate(block="true")

        else:
            log("WARNING", "Work manager '" + wm_name + "' was not found.")
            wm_report.append(["Work manager", wm_name, "Not found"])

    except:
        log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
        log("ERROR", "An error occurred when deleting work manager '" + wm_name + "'. Undoing changes...")
        wm_report.append(["Work manager", wm_name, "Failed"])
        # undo("true", "y")
        cancelEdit("y")
    
    return wm_report


def delete_queue(queue_name):
    """
    Function delete_queue finds and deletes a given queue by its name.
    Currently supporting: Queue, UniformDistributedQueue, ForeignDestination
    Input: Queue name, e.g. WLMsgQueueName1
    """
    queues_report = []
    queue_name = queue_name.strip()
    is_queue_found = False
    is_queue_skipped = False
    is_queue_deleted = False
    is_dmq_queue_deleted = False
    
    if not queue_name:
        return queues_report
    
    try:
        edit()
        startEdit()
        cd("/")
        
        my_jms_system_resources = cmo.JMSSystemResources
        
        for my_jms_system_resource in my_jms_system_resources:
            jms_module_name = my_jms_system_resource.name
            cd('/JMSSystemResources/' + jms_module_name + '/JMSResource/' + jms_module_name)
            
            # Search for the queue among Uniform Distributed queues
            queue_bean = cmo.lookupUniformDistributedQueue(queue_name)
            if queue_bean:
                is_queue_found = True
                print("")
                log("INFO", "UniformDistributedQueue '" + queue_name + "' was found in JMS module '"
                    + jms_module_name + "'")
                
                if is_standalone:
                    del_queue_choice = "Y"
                else:
                    del_queue_choice = raw_input("[INPUT] Do you want to delete this queue, Y/N [Y]? ")
                
                if del_queue_choice.upper() == "Y" or del_queue_choice.strip() == "":    
                    # Check if queue_name has an error destination (DMQ)
                    dmq_queue_bean = queue_bean.getDeliveryFailureParams().getErrorDestination()
                    
                    # Delete the queue
                    log("INFO", "Deleting UniformDistributedQueue '" + queue_name + "'...")
                    cmo.destroyUniformDistributedQueue(queue_bean)
                    log("INFO", "UniformDistributedQueue '" + queue_name + "' deleted")
                    
                    # Delete the DMQ if OK
                    if dmq_queue_bean:
                        dmq_name = dmq_queue_bean.name
                        log("INFO", "UniformDistributedQueue queue '" + queue_name 
                            + "' used Error Destination (DMQ) '" + dmq_name + "'")
    
                        if is_standalone:
                            del_queue_choice = "Y"
                        else:
                            del_queue_choice = raw_input("[INPUT] Do you want to delete this DMQ, Y/N [Y]? ")
                        
                        if del_queue_choice.upper() == "Y" or del_queue_choice.strip() == "":
                            log("INFO", "Deleting DMQ '" + dmq_name + "'...")
                            cmo.destroyUniformDistributedQueue(dmq_queue_bean)
                            log("INFO", "DMQ '" + dmq_name + "' deleted")
                            is_dmq_queue_deleted = True
                        else:
                            queues_report.append(["DMQ", dmq_name, "Skipped"])
                    
                    # Save and activate changes
                    log("INFO", "Saving changes...")
                    save()
                    log("INFO", "Activating changes...")
                    activate(block="true")
                    is_queue_deleted = True

                    # Update report
                    queues_report.append(["UniformDistributedQueue", queue_name, "Deleted"])
                    if is_dmq_queue_deleted:
                        queues_report.append(["DMQ", dmq_name, "Deleted"])
                    
                    # Stop searching in different JMS modules
                    break
                
                else:
                    log("INFO", "UniformDistributedQueue '" + queue_name + "was skipped by the user.")
                    queues_report.append(["UniformDistributedQueue", queue_name, "Skipped"])
                    cancelEdit("y")
            
            # Search for the queue_name among Queues
            else:
                queue_bean = cmo.lookupQueue(queue_name)
                if queue_bean:
                    is_queue_found = True
                    print("")
                    log("INFO", "Queue '" + queue_name + "' was found in JMS module '" + jms_module_name + "'.")
                    
                    if is_standalone:
                        del_queue_choice = "Y"
                    else:
                        del_queue_choice = raw_input("[INPUT] Do you want to delete this queue, Y/N [Y]? ")
                    
                    # Delete
                    if del_queue_choice.upper() == "Y" or del_queue_choice.strip() == "":
                         # Check if queue_name has an error destination (DMQ)
                        dmq_queue_bean = queue_bean.getDeliveryFailureParams().getErrorDestination()
                        
                        # Delete the queue
                        log("INFO", "Deleting Queue '" + queue_name + "...")
                        cmo.destroyQueue(queue_bean)
                        print("[INFO] Queue '" + queue_name + "' was deleted.")
                        
                        # Delete the DMQ if OK
                        if dmq_queue_bean:
                            dmq_name = dmq_queue_bean.name
                            log("INFO", "Queue '" + queue_name 
                                + "' used Error Destination (DMQ) '" + dmq_name + "'")
                            
                            if is_standalone:
                                del_queue_choice = "Y"
                            else:
                                del_queue_choice = raw_input("[INPUT] Do you want to delete this DMQ, Y/N [Y]? ")
                            
                            if del_queue_choice.upper() == "Y" or del_queue_choice.strip() == "":
                                log("INFO", "Deleting DMQ '" + dmq_name + "'...")
                                cmo.destroyQueue(dmq_queue_bean)
                                is_dmq_queue_deleted = True
                            else:
                                queues_report.append(["DMQ", dmq_name, "Skipped"])
                                
                        # Save and activate changes
                        log("INFO", "Saving changes...")
                        save()
                        log("INFO", "Activating changes...")
                        activate(block="true")
                        is_queue_deleted = True

                        # Update report
                        queues_report.append(["Queue", queue_name, "Deleted"])
                        if is_dmq_queue_deleted:
                            queues_report.append(["DMQ", dmq_name, "Deleted"])

                        # Stop searching in all JMS modules
                        break
                    
                    # Skip
                    else:
                        log("INFO", "UniformDistributedQueue '" + queue_name + "was skipped by the user.")
                        queues_report.append(["UniformDistributedQueue", queue_name, "Skipped"])
                        cancelEdit("y")
                
                # Search for the queue_name in all foreign servers
                else:
                    print("")
                    frn_srvs = cmo.getForeignServers()
                    
                    for frn_srv in frn_srvs:
                        fd_bean = frn_srv.lookupForeignDestination(queue_name)
                        
                        if fd_bean:
                            is_queue_found = True
                            cd('/JMSSystemResources/' + jms_module_name + '/JMSResource/' + jms_module_name
                               + '/ForeignServers/' + frn_srv.name)
                            print("")
                            log("INFO", "ForeignDestination '" + queue_name + "' was found in JMS module '"
                                + jms_module_name + "'.")
                            if is_standalone:
                                del_queue_choice = "Y"
                            else:
                                del_queue_choice = raw_input("[INPUT] Do you want to delete this queue, Y/N [Y]? ")
                            
                            # Delete
                            if del_queue_choice.upper() == "Y" or del_queue_choice.strip() == "":
                                log("INFO", "Deleting Queue '" + queue_name + "...")
                                cmo.destroyForeignDestination(fd_bean)
                                log("INFO", "ForeignDestination '" + queue_name + "' was deleted")
                                
                                log("INFO", "Saving changes...")
                                save()
                                log("INFO", "Activating changes...")
                                activate(block="true")
                                is_queue_deleted = True

                                # Update report
                                queues_report.append(["ForeignDestination", queue_name, "Deleted"])

                                # Stop searching in different Foreign Servers frn_srvs
                                break
                            
                            # Skip
                            else:
                                log("INFO", "ForeignDestination '" + queue_name + "was skipped by the user.")
                                queues_report.append(["ForeignDestination", queue_name, "Skipped"])
                                cancelEdit("y")
                    # TODO: Add topics
                    
                    # Stop searching in all JMS modules
                    if is_queue_found:
                        break

        if not is_queue_found:
            log("WARNING", "Queue '" + queue_name + "' was not found in any JMS module.")
            queues_report.append(["Queue", queue_name, "Not found"])
            cancelEdit("y")
        
        return queues_report

    except:
        print("")
        log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
        log("Info", "Discarding all changes...")
        undo("true", "y")
        cancelEdit("y")
        queues_report.append(["Queue", queue_name, "Failed"])
        return queues_report


def create_report(report_title, report, col_names, is_sorted):
    """ This function creates a tabular report with left or right text adjustment depending on the content data type.
    Input parameters:
        :param report_title: string. Serves as the report title
        :param report: list. A table (a 2D list) of data of any type (that can be cast to string)
        :param col_names: List. A list of the column names, comma separated and wrapped into [].
            Add '#' to the column name that will contain only numbers for right adjustment
            Example: ["ColTxt1", "ColNum1#", "ColTxt2"]
        :param is_sorted: Boolean. True - sort report rows, False - do not sort.
    """
    # Convert all values to strings
    report_str = []
    for row in report:
        row = [str(item) for item in row]
        report_str.append(row)

    if is_sorted:
        report_str.sort()

    # Remove "#" from headers and add to the beginning of the report
    report_str.insert(0, [col_name.replace("#", "") for col_name in col_names])

    # Count max column widths
    col_widths = [max(map(len, col)) for col in zip(*report_str)]

    # Create an underline and add to report
    underline = ["=" * width for width in col_widths]
    report_str.insert(1, underline)  # Header upper border
    report_str.insert(0, underline)  # Header lower border
    report_str.append(underline)  # Bottom line

    # Adjust columns left or right
    # rjust/ljust accept only one parameter in ver 2, therefore this workaround.
    report_adj = []
    for row in report_str:
        rw = list(zip(row, col_widths))
        row_adj = []
        for x in range(len(rw)):
            # right-adjust strings of the columns with "#" in the header and left-adjust other columns
            if "#" in col_names[x]:  # The column contains numbers
                row_adj.append(rw[x][0].rjust(rw[x][1]))
            else:
                row_adj.append(rw[x][0].ljust(rw[x][1]))
        report_adj.append(" ".join(row_adj))

    # Print the report
    f.write("\n")
    print("")
    log_report(report_title)
    for row in report_adj:
        log_report(row)
    f.write("\n")
    print("")


def cur_dt():
    """
    This function returns current local date time in %Y-%m-%d %H:%M:%S %Z format, i.e. 2018-08-27 13:28:15 CEST
    :rtype local_dt: str
    """
    local_dt = strftime("%Y-%m-%d %H:%M:%S %Z", localtime())
    return local_dt


def log(level, text):
    """
    Function log appends a log string "text" to the log file f in the format: "YYYY-MM-DD HH:mm:SS id#### [LEVEL] text"
    E.g. "2018-09-05 12:22:33 id0010 [INFO] Creating session"
    :type level: str. INFO, WARNING, ERROR
    :type text: str. The text of the log message
    """
    f.write(cur_dt() + " " + ID + " [" + level + "] " + str(text) + "\n")
    print(cur_dt() + " [" + level + "] " + str(text))


def log_report(text):
    """
    Function log_report is used for printing a report line to the standard output and the log file f.
    E.g. "2018-09-05 12:22:33 id0010 [INFO] Creating session"
    :type text: str
    """
    f.write(text + "\n")
    print(text)


def start_connect(function_name, connection_info):
    """
    This function connection to the given server if not yet connected.
    :type function_name: string. Name of the function that will be started. Used for logging.
    :type connection_info: dict. Connection information: is_connected, env, url, username, password
    :rtype: dict
    """
    log("INFO", "======================================================================")
    log("INFO", "Starting '" + function_name + "' in '" + connection_info["env"] + "'...")

    if not connection_info["is_connected"] or not connection_info["url"]:
        connection_info = connect_wls(connection_info)
    
    return connection_info


def get_avail_envs_report():
    """
    This function 
        1. Prompts for an environment from the available list
        2. Reads the properties from the corresponding property file
        3. Makes a connection to the given environment
    :type connection_info: dict. Connection information: is_connected, env, url, username, password
    :rtype: dict
    """
    prop_env_file = get_env_prop_file()
    report = []
    envs_PROD = []
    envs_TEST = []
    envs_QA = []
    envs_DEV = []
    for env in prop_env_file:
        env_group = prop_env_file.get(env).split("_")[0]
        if env_group == "PROD":
            envs_PROD.append(env)
        if env_group == "QA":
            envs_QA.append(env)
        if env_group == "TEST":
            envs_TEST.append(env)
        if env_group == "DEV":
            envs_DEV.append(env)
    envs_PROD.sort()
    envs_QA.sort()
    envs_TEST.sort()
    envs_DEV.sort()
    env_group_max = max(len(envs_PROD), len(envs_QA), len(envs_PROD), len(envs_QA), len(envs_PROD), len(envs_QA))
    envs_PROD_len = len(envs_PROD)
    envs_QA_len = len(envs_QA)
    envs_TEST_len = len(envs_TEST)
    envs_DEV_len = len(envs_DEV)
    for i in range(env_group_max):
        if envs_PROD_len > i:
            env_PROD = envs_PROD[i]
        else:
            env_PROD = ""
        if envs_QA_len > i:
            env_QA = envs_QA[i]
        else:
            env_QA = ""
        if envs_TEST_len > i:
            env_TEST = envs_TEST[i]
        else:
            env_TEST = ""
        if envs_DEV_len > i:
            env_DEV = envs_DEV[i]
        else:
            env_DEV = ""
        report.append([env_PROD, env_QA, env_TEST, env_DEV])
    return report


def connect_wls(connection_info):
    """
    This function 
        1. Prompts for an environment from the available list
        2. Reads the properties from the corresponding property file
        3. Makes a connection to the given environment
    :type connection_info: dict. Connection information: is_connected, env, url, username, password
    :rtype: dict
    """
    if connection_info["is_connected"]:
        try:
            disconnect()
        except:
            log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
            log("ERROR", "Check your connection details and retry.")
            return

    env = connection_info["env"]
    if not env:
        report = get_avail_envs_report()
        report_title = "Available environments:"
        col_names = ("PROD", "QA", "TEST", "DEV")
        create_report(report_title, report, col_names, False)

        while True:
            env = raw_input("[INPUT] Choose one environment from the list above or type 'exit' to exit to terminate the program: ")
            if env in prop_env_file:
                break
            elif env.upper() == "EXIT":
                f.close()
                exit()
            else:
                print(cur_dt() + " [WARNING] The provided environment name is not found in the list. Try again.")

    # Check the env provided when starting the script automatically
    if env in prop_env_file:
        prop_file_name = prop_env_file[env]
    elif is_standalone:
        log("ERROR", "Property file for the environment " + env + " was not found. Choose another environment or add the missing property file and restart this script.")
        f.close()
        disconnect()
        exit()
    else:
        log("ERROR", "Property file for the environment " + env + " was not found. Choose another environment or add the missing property file and restart this script.")
        is_connected = False

    # Read properties from the propery file
    in_stream = FileInputStream(prop_file_name)
    prop_file = Properties()
    prop_file.load(in_stream)
    url = prop_file.getProperty("url")
    username = prop_file.getProperty("usrname")
    password = prop_file.getProperty("password")

    log("INFO", "Trying to connect to " + url + " as " + username + "...")
    
    try:
        connect(username, password, url)
        is_connected = True
    except:
        log("ERROR", str(sys.exc_info()[0]) + " " + str(sys.exc_info()[1]))
        log("ERROR", "Check your connection details and try to reconnect")
        is_connected = False
    
    connection_info = {
        "is_connected": is_connected, 
        "env": env, 
        "url": url, 
        "username": username, 
        "password": password
    }

    return connection_info


def get_env_prop_file():
    """ 
    The function creates a dictionary of pairs of {"env": "env_property_file_name"}.
    The current directory is scanned for files with extension ".properties".
    The key part that represents the environment is received from the name of the property file 
    assuming that the environment part comes after last "_" and before the extension (.properties).
    Example of a property file name: "manageJmsQueues_DEV.properties".
    The value contains the name of the property file for the corresponding environment (key).
    :rtype: dict
    """
    prop_env_file = {}
    for f_name in os.listdir(os.getcwd()):
        if f_name.endswith('.properties'):
            # remove the part after the dot
            prop_env = f_name.split(".")[0]
            if "_" in f_name:
                # Environment name is the text that goes after the last "_"
                prop_env = prop_env.split("_")[-1]
            prop_env_file[prop_env] = f_name
    return prop_env_file


def main():
    """
    The main function. Prompts to select an action and calls the corresponding function
    """
    keep_main_loop = True
    is_connected = False
    connection_info = {"is_connected": is_connected, "env": env, "url": url, "username": username, "password": password}

    # Choose an environment and make a connection to it
    while not connection_info["is_connected"]:
        connection_info = connect_wls(connection_info)
        is_connected = connection_info["is_connected"]
        if is_standalone and not is_connected:
            f.close()
            disconnect()
            exit()
        elif not is_connected:
            connection_info["env"] = ""

    while keep_main_loop:
        if is_standalone:
            if len(sys.argv) > 1:
                procedure = sys.argv[1]
            else:
                log("ERROR", "Incomplete/incorrect list of parameters.")
                f.close()
                disconnect()
                exit()
            keep_main_loop = False
        else:
            if connection_info["env"]:
                cur_con_status = "currently connected to " + connection_info["env"]
            else:
                cur_con_status = "currently not connected"
            print("")
            print("[0] Change environment (" + cur_con_status + ")")
            print("[1] List projects deployed on server")
            print("[2] List proxy services deployed on server")
            print("[3] List business services deployed on server")
            print("[4] Undeploy OSB projects")
            print("[5] Get project details")
            print("[6] Discard open OSB sessions")
            print("[7] Disable/Enable proxy services")
            print("[8] Disable/Enable proxy service monitoring")
            print("[9] Exit")
            print("")
            while True:
                procedure = raw_input("[INPUT] Choose what you want to do from the list above: ")
                print("")
                if not procedure:
                    print(cur_dt() + " [ERROR] Input cannot be empty. Please, enter a number from 0 to 8.")
                else:
                    break
        try:
            if procedure == "0":
                connection_info["env"] = ""
                connection_info = connect_wls(connection_info)
            elif procedure == "1" or procedure == "list_projects":
                connection_info = start_connect("list_projects", connection_info)
                list_projects(connection_info)
            elif procedure == "2" or procedure == "list_proxy_services":
                connection_info = start_connect("list_proxy_services", connection_info)
                list_proxy_services(connection_info)
            elif procedure == "3" or procedure == "list_business_services":
                connection_info = start_connect("list_business_services", connection_info)
                list_business_services(connection_info)
            elif procedure == "4" or procedure == "undeploy_osb_prj":
                connection_info = start_connect("undeploy_osb_prj", connection_info)
                undeploy_osb_prj(connection_info)
            elif procedure == "5" or procedure == "get_prj_details":
                connection_info = start_connect("get_prj_details", connection_info)
                if is_standalone:
                    if len(sys.argv) >= 4:
                        report = get_prj_details(sys.argv[3])
                else:
                    report = get_prj_details("")
                if report == "Not found":
                    log("WARNING", "The project was not found")
                elif report == "Empty":
                    log("INFO", "The project was found, but does not contain either proxy or business services.")
                else:
                    report_title = "REPORT: Project details '" + connection_info["url"] + "'"
                    column_names = ("SERVICE_PATH", "ENBLD#", "URI", "WORK_MANAGER")
                    create_report(report_title, report, column_names, is_sorted=True)
                print("")
            elif procedure == "6" or procedure == "discard_sessions":
                #  start_connect("discard_sessions", is_connected)
                log("WARNING", "This operation is not yet supported")
            elif procedure == "7" or procedure == "manage_proxy_services":
                connection_info = start_connect("manage_proxy_services", connection_info)
                manage_proxy_services(connection_info)
            elif procedure == "8" or procedure == "proxy_services_monitoring":
                connection_info = start_connect("proxy_services_monitoring", connection_info)
                proxy_services_monitoring(connection_info)
            elif procedure == "9":
                break
            else:
                log("ERROR", "Unknown procedure: '" + procedure + "'. Try again.")

        except (WLSTException, ValueError, NameError, Exception, AttributeError, EOFError), e:
            log("ERROR", str(e))
            disconnect()
            is_connected = False
            connection_info["is_connected"] = is_connected
            raise

    f.close()
    disconnect()
    exit()


# Create a four digit random id left padded with zeros for logging
n = random.randint(1, 1000)
ID = "id" + str("%04d" % n)

# Name of the log file is derived from the name of the script
log_file = sys.argv[0].replace("py", "log")
f = open(log_file, "a")
print(cur_dt() + " [INFO] Output is sent to '" + log_file + "'. Log ID = '" + ID + "'")

prop_env_file = get_env_prop_file()

if len(sys.argv) > 1:
    is_standalone = True
else:
    is_standalone = False

if len(sys.argv) > 1:
    env = sys.argv[2]
else:
    env = ""

url = ""
username = ""
password = ""

main()
