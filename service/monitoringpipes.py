#!/usr/bin/env python3

import logging
import os
import sys
from enum import Enum

import requests
from requests.exceptions import ConnectionError
from requests.exceptions import Timeout
from statuspage import StatusPageConnection

__author__ = "Ravish Ranjan"

required_env_vars = ["api_key", "jwt", "page_id", "sesam_node_url", "status_page_groups"]


class AppConfig(object):
    pass


class ComponentStatusEnum(Enum):
    OPERATIONAL = 'operational'
    MAINTENANCE = "under_maintenance"
    DEGRADED = 'degraded_performance'
    PARTIAL = 'partial_outage'
    MAJOR = 'major_outage'


config = AppConfig()

# load variables
missing_env_vars = list()
for env_var in required_env_vars:
    value = os.getenv(env_var)
    if not value:
        missing_env_vars.append(env_var)
    setattr(config, env_var, value)

# logging settings
logger = logging.getLogger('status_page_manager')
logger.setLevel({"INFO": logging.INFO,
                 "DEBUG": logging.DEBUG,
                 "WARNING": logging.WARNING,
                 "ERROR": logging.ERROR}.get(os.getenv("LOG_LEVEL", "INFO")))  # Default log level: INFO

stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
logger.addHandler(stdout_handler)

logger.info(f"SESAM instance name {config.sesam_node_url}")

status_page_conn = StatusPageConnection(config.api_key, config.page_id)

# Global variable
node_all_pipes = list()


def prepare_payload():
    pipe_list = get_pipes_for_status_page()
    component_group_list = status_page_conn.get_status_page_component_group_list()
    component_list = status_page_conn.get_status_page_component_list()

    valid_component_groups = [g for g in component_group_list if
                              g['GroupName'] in config.status_page_groups]

    if valid_component_groups:
        if pipe_list:
            for pipe in pipe_list:
                for group in pipe['Pipe_Status_Page_Groups']:
                    if group not in [g['GroupName'] for g in valid_component_groups]:
                        logger.error(f"Nothing will happen for invalid group "
                                     f"Name: \"{group}\" provided for pipe: \"{pipe['Name']}\"")

            unknown_pipes = unknown_node_pipes_on_status_page()

            for valid_group in valid_component_groups:
                # Creation of component  if required:
                create_component(component_list, valid_group, pipe_list)
                # updating component  if required:
                update_component(component_list, valid_group, pipe_list)
                # Deletion of components if required :
                delete_component(component_list, valid_group, pipe_list, unknown_pipes)
    else:
        logger.info(f"No Valid Group Name provided in environmental "
                    f"variable \"status_page_groups\" .So, doing nothing.")


def filter_pipes_for_status_page():
    global node_all_pipes
    node_all_pipes = get_sesam_node_pipe_list()
    try:
        filter_pipes = list()
        keys = ['Name', 'Status', 'Pipe_Status_Page_Groups']
        for each_pipe in node_all_pipes:
            if each_pipe['config']['original'].get('metadata') is not None and \
                    each_pipe['config']['original']['metadata'].get('statuspage') is not None:
                pipe_id = each_pipe['_id']
                status_groups_name = each_pipe['config']['original']['metadata']['statuspage']
                status = ComponentStatusEnum.OPERATIONAL.value  # By default , it would be operational
                filter_pipes.append(dict(zip(keys, [pipe_id, status, status_groups_name])))
        return filter_pipes
    except Exception as e:
        logger.error(f"Issue while filtering pipes: {each_pipe['_id']} for status page,got error: {e}")
        return filter_pipes  # Send valid pipes if any for further processing before occurring issue.


def get_pipes_for_status_page():
    filter_node_pipes = filter_pipes_for_status_page()
    if filter_node_pipes:
        try:
            response = requests.get(url='https://portal.sesam.io/api/notifications-summary',
                                    timeout=180,
                                    headers={'Authorization': 'bearer ' + config.jwt})
            if response.ok:
                pipe_status_list = response.json()
                for each_filter_pipe_item in filter_node_pipes:
                    for each_status_pipe in pipe_status_list:
                        if each_status_pipe.get('pipe_id') is not None and each_status_pipe['pipe_id'] == \
                                each_filter_pipe_item['Name']:
                            if each_status_pipe['status'] != 'ok':
                                notifications_list = each_status_pipe['notifications']
                                each_filter_pipe_item['Status'] = get_status(notifications_list)
                return filter_node_pipes
            else:
                logger.error(f"Issue while fetching notifications-rule from portal, "
                             f"g__len__ = {int} 4ot status code {response.status_code} ")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Issue while fetching notifications-rule from portal {e}")
            sys.exit(1)


def get_status(notifications_list):
    if notifications_list:
        for each_notifications in notifications_list:
            if each_notifications['notification_rule_name'].startswith("partial"):
                return ComponentStatusEnum.PARTIAL.value
        return ComponentStatusEnum.MAJOR.value
    else:
        # In case  of no notifications rule, return major outage for 'failed' pipe-status.
        return ComponentStatusEnum.MAJOR.value


def get_sesam_node_pipe_list():
    try:
        response = requests.get(url=config.sesam_node_url + "/pipes", timeout=180,
                                headers={'Authorization': 'bearer ' + config.jwt})
        if response.ok:
            return response.json()
        else:
            logger.error(f"Issue while fetching node-pipes, got error {response.status_code}")
            sys.exit(1)
    except Timeout as e:
        logger.error(f"Timeout issue while fetching node pipes {e}")
        update_all_component_directly(ComponentStatusEnum.DEGRADED.value)
        sys.exit(1)
    except ConnectionError as e:
        logger.error(f"ConnectionError issue while fetching node pipes {e}")
        update_all_component_directly(ComponentStatusEnum.MAJOR.value)
        sys.exit(1)
    except Exception as e:
        logger.error(f"issue while fetching node pipes {e}")
        sys.exit(1)


def update_all_component_directly(status):
    component_group_list = status_page_conn.get_status_page_component_group_list()
    component_list = status_page_conn.get_status_page_component_list()

    valid_component_groups = [g for g in component_group_list if
                              g['GroupName'] in config.status_page_groups]

    if valid_component_groups:
        # updating the component with based on error message:
        for valid_group in valid_component_groups:
            update_payload_list = [d for d in component_list if d['GroupId'] == valid_group['GroupId']]
            if update_payload_list:
                for update_item in update_payload_list:
                    update_item['Status'] = status
                    update_item.update({'GroupName': valid_group['GroupName']})
                    status_page_conn.update_component_status_page(update_item)

    else:
        logger.info(f"No Valid Group Name provided in environmental "
                    f"variable \"status_page_groups\" .So, doing nothing.")


def unknown_node_pipes_on_status_page():
    try:
        unknown_pipe_list = list()
        keys = ['Name']
        for each_pipe in node_all_pipes:  # use the global variable & save one call to SESAM api.
            if each_pipe['config']['original'].get('metadata') is None or (
                    each_pipe['config']['original'].get('metadata') is not None and
                    each_pipe['config']['original']['metadata'].get('statuspage') is None):
                pipe_id = each_pipe['_id']
                unknown_pipe_list.append(dict(zip(keys, [pipe_id])))
        return unknown_pipe_list
    except Exception as e:
        logger.error(f"issue while filtering pipes inside method unknown_pipes_of_statuspage {e}")


def create_component(component_list, valid_group, pipe_list):
    create_payload_list = [d for d in pipe_list if d['Name'] not in [p['Name'] for p in component_list
                                                                     if p['GroupId'] == valid_group['GroupId']] and
                           valid_group['GroupName'] in d['Pipe_Status_Page_Groups']]
    if create_payload_list:
        for create_item in create_payload_list:
            create_payload = dict()
            create_payload['Name'] = create_item['Name']
            create_payload['Group_Id'] = valid_group['GroupId']
            create_payload['Status'] = create_item['Status']
            create_payload['GroupName'] = valid_group['GroupName']
            status_page_conn.create_component_status_page(create_payload)


def update_component(component_list, valid_group, pipe_list):
    update_payload_list = [d for d in component_list for x in pipe_list if d['Name'] == x['Name'] and
                           d['Status'] != x['Status'] and valid_group['GroupName'] in x['Pipe_Status_Page_Groups']
                           and d['GroupId'] == valid_group['GroupId']]

    if update_payload_list:
        for update_item in update_payload_list:
            d = next(item for item in pipe_list if item['Name'] == update_item['Name'])
        update_item['Status'] = d['Status']
        update_item.update({'GroupName': valid_group['GroupName']})
        status_page_conn.update_component_status_page(update_item)


def delete_component(component_list, valid_group, pipe_list, unknown_pipes):
    delete_payload_list = [d for d in component_list for x in pipe_list if d['Name'] == x['Name'] and
                           d['GroupId'] == valid_group['GroupId'] and d['Status'] != ComponentStatusEnum.MAJOR.value and
                           valid_group['GroupName'] not in x['Pipe_Status_Page_Groups']]

    if delete_payload_list:
        for delete_item in delete_payload_list:
            # Adding a new key value pair to just log Group Name
            delete_item['Status'] = ComponentStatusEnum.MAJOR.value
            delete_item.update({'GroupName': valid_group['GroupName']})
            # No hard delete only change the status and Admin of status page will decide to keep it or not.
            status_page_conn.update_component_status_page(delete_item)

    # delete un-wanted or unknown components if any from status-page (clean-up task)
    unknown_delete_payload_list = [d for d in component_list for x in unknown_pipes
                                   if d['Name'] == x['Name'] and d['Status'] != ComponentStatusEnum.MAJOR.value
                                   and d['GroupId'] == valid_group['GroupId']]

    if unknown_delete_payload_list:
        for unknown_delete_item in unknown_delete_payload_list:
            unknown_delete_item['Status'] = ComponentStatusEnum.MAJOR.value
            unknown_delete_item.update({'GroupName': valid_group['GroupName']})
            # No hard delete only change the status.
            status_page_conn.update_component_status_page(unknown_delete_item)


if __name__ == '__main__':
    if len(missing_env_vars) != 0:
        logger.error(f"Missing the following required environment variable(s) {missing_env_vars}")
        sys.exit(1)
    else:
        prepare_payload()


